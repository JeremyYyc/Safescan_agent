import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Callable
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from safescan_common.http.errors import ApiError

from app.clients.identity import IdentityClient
from app.core.config import Settings
from app.core.cache import QueryCache
from app.core.errors import action_forbidden, error, resource_not_found, state_conflict, version_conflict
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.principal import Principal
from app.models.tables import (Application, Building, ContactMessage, ContactThread,
                               CustomerEventVersion, CustomerLeaseSlot, IdempotencyRecord, Lease,
                               LeaseDocument, LeaseSignatureEvent, LeaseTenant, OutboxEvent, Party,
                               Property, ProspectCase, ProspectCaseEvent, RentInvoice,
                               StaffBuildingScope, StaffPropertyScope)


ACTIVE_LEASE_STATES = {"pending_signature", "executed", "active"}
ELIGIBLE_CUSTOMER_STATES = {"prospect", "former_tenant"}


class LeasingService:
    def __init__(self, session: Session, identity: IdentityClient, settings: Settings,
                 cache: QueryCache | None = None) -> None:
        self.db = session
        self.identity = identity
        self.settings = settings
        self.cache = cache

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def _transaction(self, callback: Callable[[], dict]) -> dict:
        try:
            result = callback()
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def _idempotency_start(self, actor: Principal, operation: str, key: UUID, payload: dict) -> tuple[str, dict | None]:
        digest = hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        lock_key = f"{actor.subject_id}:{operation}:{key}"
        self.db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                        {"key": lock_key})
        record = self.db.scalar(sa.select(IdempotencyRecord).where(
            IdempotencyRecord.actor_subject_id == actor.subject_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        ))
        if record:
            if record.request_hash != digest:
                raise error(409, "idempotency_conflict", "Idempotency key was used for another request",
                            operation=operation)
            return digest, record.response_body
        return digest, None

    def _idempotency_finish(self, actor: Principal, operation: str, key: UUID, digest: str,
                            body: dict, status: int = 200, resource_id: UUID | None = None) -> None:
        self.db.add(IdempotencyRecord(
            actor_subject_id=actor.subject_id, operation=operation, idempotency_key=key,
            request_hash=digest, response_status=status, response_body=jsonable_encoder(body),
            resource_id=resource_id, expires_at=self.now() + timedelta(hours=self.settings.idempotency_ttl_hours),
        ))

    def _outbox(self, event_type: str, aggregate_type: str, aggregate_id: UUID,
                aggregate_version: int, correlation_id: UUID, payload: dict) -> None:
        self.db.add(OutboxEvent(
            event_id=uuid4(), event_type=event_type, schema_version=1,
            aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            aggregate_version=aggregate_version, correlation_id=correlation_id,
            payload=jsonable_encoder(payload), status="pending", attempts=0, available_at=self.now(),
        ))

    def _next_customer_version(self, subject_id: UUID) -> int:
        version = self.db.scalar(sa.select(CustomerEventVersion).where(
            CustomerEventVersion.customer_subject_id == subject_id).with_for_update())
        if version is None:
            version = CustomerEventVersion(customer_subject_id=subject_id, aggregate_version=1)
            self.db.add(version)
            self.db.flush()
            return 1
        version.aggregate_version += 1
        return version.aggregate_version

    def _party_for(self, subject_id: UUID, *, create: bool = False, name: str = "Customer") -> Party | None:
        party = self.db.scalar(sa.select(Party).where(Party.subject_id == subject_id))
        if party is None and create:
            party = Party(party_type="person", subject_id=subject_id, name=name,
                          contact={}, status="active")
            self.db.add(party)
            self.db.flush()
        return party

    def _property(self, public_id: UUID, *, lock: bool = False) -> Property:
        query = sa.select(Property).where(Property.public_id == public_id)
        if lock:
            query = query.with_for_update()
        value = self.db.scalar(query)
        if not value:
            raise resource_not_found("property_not_visible")
        return value

    def _case(self, public_id: UUID, *, lock: bool = False) -> ProspectCase:
        query = sa.select(ProspectCase).where(ProspectCase.public_id == public_id)
        if lock:
            query = query.with_for_update()
        value = self.db.scalar(query)
        if not value:
            raise resource_not_found("prospect_case_not_found")
        return value

    def _application(self, public_id: UUID, *, lock: bool = False) -> Application:
        query = sa.select(Application).where(Application.public_id == public_id)
        if lock:
            query = query.with_for_update()
        value = self.db.scalar(query)
        if not value:
            raise resource_not_found("resource_not_found")
        return value

    def _lease(self, public_id: UUID, *, lock: bool = False) -> Lease:
        query = sa.select(Lease).where(Lease.public_id == public_id)
        if lock:
            query = query.with_for_update()
        value = self.db.scalar(query)
        if not value:
            raise resource_not_found("lease_access_required")
        return value

    def _customer_owns_case(self, actor: Principal, case: ProspectCase) -> bool:
        return bool(self.db.scalar(sa.select(Party.id).where(
            Party.id == case.prospect_party_id, Party.subject_id == actor.subject_id)))

    def _staff_property_access(self, actor: Principal, property_row: Property) -> bool:
        if actor.account_type != "staff" or not actor.staff_id:
            return False
        if actor.is_admin or actor.has("property:read_market") or actor.has("property:manage_vacancy"):
            return True
        now = self.now()
        direct = self.db.scalar(sa.select(StaffPropertyScope.id).where(
            StaffPropertyScope.staff_id == actor.staff_id,
            StaffPropertyScope.property_id == property_row.id,
            StaffPropertyScope.valid_from <= now,
            sa.or_(StaffPropertyScope.valid_until.is_(None), StaffPropertyScope.valid_until > now),
        ))
        building = None
        if property_row.building_id:
            building = self.db.scalar(sa.select(StaffBuildingScope.id).where(
                StaffBuildingScope.staff_id == actor.staff_id,
                StaffBuildingScope.building_id == property_row.building_id,
                StaffBuildingScope.valid_from <= now,
                sa.or_(StaffBuildingScope.valid_until.is_(None), StaffBuildingScope.valid_until > now),
            ))
        return bool(direct or building)

    def _staff_case_access(self, actor: Principal, case: ProspectCase) -> bool:
        return bool(actor.account_type == "staff" and actor.staff_id and
                    (actor.is_admin or case.assigned_consultant_staff_id == actor.staff_id))

    def _require_customer_eligible(self, actor: Principal) -> None:
        if actor.account_type != "customer" or actor.customer_status not in ELIGIBLE_CUSTOMER_STATES:
            raise error(403, "customer_not_eligible_for_lease",
                        "Customer is not eligible for a new lease",
                        customer_status=actor.customer_status,
                        allowed_statuses=sorted(ELIGIBLE_CUSTOMER_STATES))

    @staticmethod
    def _property_view(row: Property) -> dict:
        building = row.building
        return {
            "id": str(row.public_id), "reference": row.reference, "address": row.address,
            "location": {"address": row.address,
                         "latitude": str(row.latitude) if row.latitude is not None else None,
                         "longitude": str(row.longitude) if row.longitude is not None else None},
            "building_id": str(building.public_id) if building else None,
            "building": ({"id": str(building.public_id), "reference": building.reference,
                          "name": building.name, "address": building.address,
                          "timezone": building.timezone} if building else None),
            "bedrooms": row.bedrooms, "bathrooms": str(row.bathrooms),
            "parking_spaces": row.parking_spaces,
            "has_parking": row.parking_spaces > 0 if row.parking_spaces is not None else None,
            "floor_area_sqm": (str(row.floor_area_sqm)
                               if row.floor_area_sqm is not None else None),
            "display_image_urls": row.display_image_urls or [],
            "floorplan_url": row.floorplan_url,
            "weekly_rent": str(row.weekly_rent), "currency": row.currency,
            "status": row.status, "availability": "available" if row.status == "marketing" else "unavailable",
            "attributes": row.attributes or {}, "updated_at": row.updated_at or row.created_at,
        }

    @staticmethod
    def _stable_consultant(customer_subject_id: UUID, property_id: UUID,
                           consultant_ids: list[UUID]) -> UUID | None:
        if not consultant_ids:
            return None
        seed = hashlib.sha256(f"{customer_subject_id}:{property_id}".encode()).digest()
        ordered = sorted(consultant_ids, key=str)
        return ordered[int.from_bytes(seed[:8], "big") % len(ordered)]

    def market_properties(self, *, q: str | None, bedrooms: int | None, min_rent: Decimal | None,
                          max_rent: Decimal | None, cursor: str | None, limit: int) -> dict:
        cache_key = None
        if self.cache:
            cache_key = "leasing:market:list:" + self.cache.market_epoch() + ":" + hashlib.sha256(
                json.dumps({"q": q, "bedrooms": bedrooms, "min": str(min_rent), "max": str(max_rent),
                            "cursor": cursor, "limit": limit}, sort_keys=True).encode()).hexdigest()
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        query = sa.select(Property).where(Property.listing_visibility == "public",
                                          Property.status == "marketing")
        if q:
            query = query.where(sa.or_(Property.address.ilike(f"%{q}%"),
                                       Property.reference.ilike(f"%{q}%")))
        if bedrooms is not None:
            query = query.where(Property.bedrooms == bedrooms)
        if min_rent is not None:
            query = query.where(Property.weekly_rent >= min_rent)
        if max_rent is not None:
            query = query.where(Property.weekly_rent <= max_rent)
        decoded = decode_cursor(cursor)
        if decoded:
            created, row_id = decoded
            query = query.where(sa.tuple_(Property.created_at, Property.id) < (created, row_id))
        rows = list(self.db.scalars(query.order_by(Property.created_at.desc(), Property.id.desc())
                                    .limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        result = {"items": [self._property_view(row) for row in rows[:limit]], "next_cursor": next_cursor}
        if self.cache and cache_key:
            self.cache.set(cache_key, result, 60)
        return result

    def market_property(self, property_id: UUID) -> dict:
        cache_key = f"leasing:market:detail:{self.cache.market_epoch()}:{property_id}" if self.cache else None
        if self.cache and cache_key:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        row = self.db.scalar(sa.select(Property).where(Property.public_id == property_id,
                                                       Property.listing_visibility == "public",
                                                       Property.status == "marketing"))
        if not row:
            raise resource_not_found("property_not_visible")
        result = self._property_view(row)
        if self.cache and cache_key:
            self.cache.set(cache_key, result, 90)
        return result

    def staff_properties(self, actor: Principal, *, status: str | None, building_id: UUID | None,
                         cursor: str | None, limit: int) -> dict:
        if actor.account_type != "staff" or not actor.staff_id:
            raise action_forbidden()
        query = sa.select(Property)
        if status:
            query = query.where(Property.status == status)
        if building_id:
            query = query.join(Building, Building.id == Property.building_id).where(Building.public_id == building_id)
        if not (actor.is_admin or actor.has("property:read_market") or actor.has("property:manage_vacancy")):
            now = self.now()
            query = query.where(sa.or_(
                sa.exists(sa.select(StaffPropertyScope.id).where(
                    StaffPropertyScope.staff_id == actor.staff_id,
                    StaffPropertyScope.property_id == Property.id,
                    StaffPropertyScope.valid_from <= now,
                    sa.or_(StaffPropertyScope.valid_until.is_(None), StaffPropertyScope.valid_until > now))),
                sa.exists(sa.select(StaffBuildingScope.id).where(
                    StaffBuildingScope.staff_id == actor.staff_id,
                    StaffBuildingScope.building_id == Property.building_id,
                    StaffBuildingScope.valid_from <= now,
                    sa.or_(StaffBuildingScope.valid_until.is_(None), StaffBuildingScope.valid_until > now))),
            ))
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(sa.tuple_(Property.created_at, Property.id) < decoded)
        rows = list(self.db.scalars(query.order_by(Property.created_at.desc(), Property.id.desc())
                                    .limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        return {"items": [self._property_view(row) for row in rows[:limit]], "next_cursor": next_cursor}

    def staff_property(self, actor: Principal, property_id: UUID) -> dict:
        row = self._property(property_id)
        if not self._staff_property_access(actor, row):
            raise resource_not_found()
        body = self._property_view(row)
        lease = self.db.scalar(sa.select(Lease).where(
            Lease.property_id == row.id, Lease.status.in_(ACTIVE_LEASE_STATES))
            .order_by(Lease.starts_on).limit(1))
        body["current_lease"] = ({"id": str(lease.public_id), "status": lease.status,
                                  "starts_on": lease.starts_on, "ends_on": lease.ends_on}
                                 if lease else None)
        return body

    def buildings(self, actor: Principal) -> dict:
        if actor.account_type != "staff" or not actor.staff_id:
            raise action_forbidden()
        query = sa.select(Building).where(Building.status == "active")
        if not actor.is_admin:
            now = self.now()
            query = query.where(sa.exists(sa.select(StaffBuildingScope.id).where(
                StaffBuildingScope.staff_id == actor.staff_id,
                StaffBuildingScope.building_id == Building.id,
                StaffBuildingScope.valid_from <= now,
                sa.or_(StaffBuildingScope.valid_until.is_(None), StaffBuildingScope.valid_until > now))))
        rows = list(self.db.scalars(query.order_by(Building.name, Building.id)))
        return {"items": [{"id": str(row.public_id), "reference": row.reference, "name": row.name,
                           "address": row.address, "timezone": row.timezone} for row in rows]}

    def contact(self, actor: Principal, data: dict, key: UUID, correlation_id: UUID) -> dict:
        if actor.account_type != "customer":
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "contact_request", key, data)
            if replay is not None:
                return replay
            prop = self._property(data["property_id"], lock=True)
            if prop.listing_visibility != "public" or prop.status != "marketing":
                raise resource_not_found("property_not_visible")
            party = self._party_for(actor.subject_id, create=True, name=data.get("customer_name", "Customer"))
            case = self.db.scalar(sa.select(ProspectCase).where(
                ProspectCase.prospect_party_id == party.id, ProspectCase.property_id == prop.id,
                ProspectCase.status == "open").with_for_update())
            if not case:
                try:
                    active_consultants = self.identity.active_leasing_consultants()
                except ApiError:
                    # Capturing the lead is more important than assignment availability. Identity
                    # is still authoritative: a failed lookup creates an unassigned case for admin
                    # recovery rather than trusting stale or locally configured staff IDs.
                    active_consultants = []
                selected = self._stable_consultant(
                    actor.subject_id, prop.public_id,
                    [UUID(value["id"]) for value in active_consultants],
                )
                if selected:
                    try:
                        self.identity.require_active_leasing_consultant(selected)
                    except ApiError as exc:
                        if exc.code != "leasing_consultant_unavailable":
                            raise
                        selected = None
                case = ProspectCase(prospect_party_id=party.id, property_id=prop.id,
                                    assigned_consultant_staff_id=selected, stage="contacted", status="open",
                                    opened_at=self.now(), version=1)
                self.db.add(case)
                self.db.flush()
                self._case_event(case, "contacted", None, "contacted", actor.subject_id,
                                 {"assignment_status": "assigned" if selected else "unassigned"})
            thread = self.db.scalar(sa.select(ContactThread).where(
                ContactThread.prospect_case_id == case.id, ContactThread.status == "active").with_for_update())
            if not thread:
                thread = ContactThread(prospect_case_id=case.id,
                                       assigned_consultant_staff_id=case.assigned_consultant_staff_id,
                                       status="active", next_sequence=1)
                self.db.add(thread)
                self.db.flush()
            message = ContactMessage(thread_id=thread.id, sequence_no=thread.next_sequence,
                                     sender_type="prospect", sender_subject_id=actor.subject_id,
                                     sender_staff_id=None, content=data["content"], status="sent",
                                     sent_at=self.now(), client_message_id=data["client_message_id"])
            thread.next_sequence += 1
            thread.last_message_at = message.sent_at
            self.db.add(message)
            self.db.flush()
            body = self._case_view(case)
            body["thread"] = {"id": str(thread.public_id),
                              "last_message_sequence": message.sequence_no}
            self._outbox("prospect.case_changed.v1", "prospect_case", case.public_id, case.version,
                         correlation_id, {**body, "assigned_staff_id": str(case.assigned_consultant_staff_id)
                                          if case.assigned_consultant_staff_id else None})
            self._idempotency_finish(actor, "contact_request", key, digest, body, 201, case.public_id)
            return body

        return self._transaction(command)

    def _case_event(self, case: ProspectCase, event_type: str, from_stage: str | None,
                    to_stage: str | None, actor_subject: UUID | None, details: dict) -> None:
        sequence = self.db.scalar(sa.select(sa.func.coalesce(sa.func.max(ProspectCaseEvent.sequence_no), 0))
                                  .where(ProspectCaseEvent.prospect_case_id == case.id)) + 1
        self.db.add(ProspectCaseEvent(prospect_case_id=case.id, sequence_no=sequence,
                                     event_type=event_type, from_stage=from_stage, to_stage=to_stage,
                                     actor_subject_id=actor_subject, occurred_at=self.now(),
                                     details_redacted=details))

    def _case_view(self, case: ProspectCase) -> dict:
        prop = self.db.get(Property, case.property_id)
        property_view = ({"id": str(prop.public_id), "reference": prop.reference,
                          "address": prop.address} if prop else None)
        return {"id": str(case.public_id), "property": property_view, "stage": case.stage,
                "status": case.status, "assigned_consultant": ({"id": str(case.assigned_consultant_staff_id)}
                if case.assigned_consultant_staff_id else None), "version": case.version,
                "updated_at": case.updated_at or case.created_at}

    def cases(self, actor: Principal, *, stage: str | None, status: str | None,
              cursor: str | None, limit: int) -> dict:
        query = sa.select(ProspectCase)
        if actor.account_type == "customer":
            party = self._party_for(actor.subject_id)
            if not party:
                return {"items": [], "next_cursor": None}
            query = query.where(ProspectCase.prospect_party_id == party.id)
        elif actor.account_type == "staff" and actor.staff_id:
            if not actor.is_admin:
                query = query.where(ProspectCase.assigned_consultant_staff_id == actor.staff_id)
        else:
            raise action_forbidden()
        if stage:
            query = query.where(ProspectCase.stage == stage)
        if status:
            query = query.where(ProspectCase.status == status)
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(sa.tuple_(ProspectCase.created_at, ProspectCase.id) < decoded)
        rows = list(self.db.scalars(query.order_by(ProspectCase.created_at.desc(), ProspectCase.id.desc())
                                    .limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        return {"items": [self._case_view(row) for row in rows[:limit]], "next_cursor": next_cursor}

    def get_case(self, actor: Principal, case_id: UUID) -> dict:
        case = self._case(case_id)
        if not (self._customer_owns_case(actor, case) or self._staff_case_access(actor, case)):
            raise resource_not_found("case_access_denied")
        return self._case_view(case)

    def update_case(self, actor: Principal, case_id: UUID, data: dict, correlation_id: UUID) -> dict:
        def command() -> dict:
            case = self._case(case_id, lock=True)
            if not self._staff_case_access(actor, case):
                raise resource_not_found("case_access_denied")
            if case.version != data["version"]:
                raise version_conflict(case.version)
            previous = case.stage
            if data.get("stage"):
                case.stage = data["stage"]
            if data.get("status"):
                case.status = data["status"]
                if case.status == "closed":
                    case.closed_at = self.now()
            case.version += 1
            self._case_event(case, "stage_changed", previous, case.stage, actor.subject_id,
                             {"reason": data.get("reason")})
            body = self._case_view(case)
            self._outbox("prospect.case_changed.v1", "prospect_case", case.public_id, case.version,
                         correlation_id, body)
            return body
        return self._transaction(command)

    def assign_case(self, actor: Principal, case_id: UUID, data: dict, key: UUID,
                    correlation_id: UUID) -> dict:
        if actor.account_type != "staff" or not actor.staff_id or not actor.has("prospect:manage_all"):
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "prospect_case_assign", key, data)
            if replay is not None:
                return replay
            case = self._case(case_id, lock=True)
            if case.status != "open":
                raise state_conflict("prospect_case_closed", case.status, ["open"])
            if case.version != data["version"]:
                raise version_conflict(case.version)
            consultant = self.identity.require_active_leasing_consultant(
                data["consultant_staff_id"]
            )
            previous = case.assigned_consultant_staff_id
            case.assigned_consultant_staff_id = data["consultant_staff_id"]
            case.version += 1
            self.db.execute(sa.update(ContactThread).where(
                ContactThread.prospect_case_id == case.id,
                ContactThread.status == "active",
            ).values(assigned_consultant_staff_id=data["consultant_staff_id"],
                     updated_at=self.now()))
            self._case_event(case, "consultant_reassigned", case.stage, case.stage,
                             actor.subject_id,
                             {"from_staff_id": str(previous) if previous else None,
                              "to_staff_id": str(data["consultant_staff_id"]),
                              "reason": data["reason"]})
            body = self._case_view(case)
            body["assigned_consultant"] = consultant
            self._outbox("prospect.case_changed.v1", "prospect_case", case.public_id,
                         case.version, correlation_id, body)
            self._idempotency_finish(actor, "prospect_case_assign", key, digest, body,
                                     resource_id=case.public_id)
            return body

        return self._transaction(command)

    def case_events(self, actor: Principal, case_id: UUID, after: int, limit: int) -> dict:
        case = self._case(case_id)
        if not (self._customer_owns_case(actor, case) or self._staff_case_access(actor, case)):
            raise resource_not_found("case_access_denied")
        rows = list(self.db.scalars(sa.select(ProspectCaseEvent).where(
            ProspectCaseEvent.prospect_case_id == case.id, ProspectCaseEvent.sequence_no > after)
            .order_by(ProspectCaseEvent.sequence_no).limit(limit)))
        return {"items": [{"sequence": row.sequence_no, "type": row.event_type,
                           "from_stage": row.from_stage, "to_stage": row.to_stage,
                           "occurred_at": row.occurred_at} for row in rows]}

    def messages(self, actor: Principal, thread_id: UUID, after: int, limit: int) -> dict:
        thread = self.db.scalar(sa.select(ContactThread).where(ContactThread.public_id == thread_id))
        if not thread:
            raise resource_not_found()
        case = self.db.get(ProspectCase, thread.prospect_case_id)
        if not (self._customer_owns_case(actor, case) or self._staff_case_access(actor, case)):
            raise resource_not_found("case_access_denied")
        rows = list(self.db.scalars(sa.select(ContactMessage).where(
            ContactMessage.thread_id == thread.id, ContactMessage.sequence_no > after,
            ContactMessage.status != "deleted").order_by(ContactMessage.sequence_no).limit(limit)))
        return {"items": [{"sequence": row.sequence_no, "sender_type": row.sender_type,
                           "content": row.content, "sent_at": row.sent_at} for row in rows]}

    def post_message(self, actor: Principal, thread_id: UUID, data: dict) -> dict:
        def command() -> dict:
            thread = self.db.scalar(sa.select(ContactThread).where(
                ContactThread.public_id == thread_id).with_for_update())
            if not thread:
                raise resource_not_found()
            case = self.db.get(ProspectCase, thread.prospect_case_id)
            customer = self._customer_owns_case(actor, case)
            staff = self._staff_case_access(actor, case)
            if not (customer or staff):
                raise resource_not_found("case_access_denied")
            existing = self.db.scalar(sa.select(ContactMessage).where(
                ContactMessage.thread_id == thread.id,
                ContactMessage.client_message_id == data["client_message_id"]))
            if existing:
                return {"sequence": existing.sequence_no, "content": existing.content,
                        "sent_at": existing.sent_at}
            row = ContactMessage(thread_id=thread.id, sequence_no=thread.next_sequence,
                                 sender_type="prospect" if customer else "staff",
                                 sender_subject_id=actor.subject_id if customer else None,
                                 sender_staff_id=actor.staff_id if staff else None,
                                 content=data["content"], status="sent", sent_at=self.now(),
                                 client_message_id=data["client_message_id"])
            thread.next_sequence += 1
            thread.last_message_at = row.sent_at
            self.db.add(row)
            self.db.flush()
            return {"sequence": row.sequence_no, "content": row.content, "sent_at": row.sent_at}
        return self._transaction(command)

    @staticmethod
    def _application_view(row: Application) -> dict:
        return {"id": str(row.public_id), "reference": row.reference,
                "case_id": None, "property_id": None, "status": row.status,
                "desired_start_on": row.desired_start_on, "term_months": row.term_months,
                "occupants": row.occupants, "note": row.note or "", "version": row.version,
                "submitted_at": row.submitted_at, "decided_at": row.decided_at,
                "closed_reason": row.closed_reason, "closed_at": row.closed_at,
                "winning_lease_id": None, "updated_at": row.updated_at or row.created_at}

    def _full_application_view(self, row: Application) -> dict:
        body = self._application_view(row)
        case = self.db.get(ProspectCase, row.prospect_case_id)
        prop = self.db.get(Property, row.property_id)
        winner = self.db.get(Lease, row.winning_lease_id) if row.winning_lease_id else None
        body.update(case_id=str(case.public_id), property_id=str(prop.public_id),
                    winning_lease_id=str(winner.public_id) if winner else None)
        return body

    def _application_access(self, actor: Principal, application: Application) -> bool:
        case = self.db.get(ProspectCase, application.prospect_case_id)
        return self._customer_owns_case(actor, case) or self._staff_case_access(actor, case)

    def create_application(self, actor: Principal, data: dict, key: UUID,
                           correlation_id: UUID) -> dict:
        self._require_customer_eligible(actor)

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "application_create", key, data)
            if replay is not None:
                return replay
            case = self._case(data["case_id"], lock=True)
            if not self._customer_owns_case(actor, case) or case.status != "open":
                raise resource_not_found("case_access_denied")
            prop = self._property(data["property_id"], lock=True)
            if case.property_id != prop.id:
                raise error(409, "application_state_conflict", "Case and property do not match")
            if prop.status not in {"marketing", "under_offer"}:
                raise error(409, "property_no_longer_available", "Property is no longer available",
                            availability="unavailable")
            party = self._party_for(actor.subject_id)
            reference = f"APP-{self.now():%Y%m%d}-{uuid4().hex[:10].upper()}"
            row = Application(prospect_case_id=case.id, property_id=prop.id, applicant_id=party.id,
                              reference=reference, status="draft",
                              desired_start_on=data["desired_start_on"], term_months=data["term_months"],
                              occupants=data["occupants"], note=data.get("note"), version=1)
            self.db.add(row)
            case.stage = "application"
            case.version += 1
            self._case_event(case, "application_created", None, "application", actor.subject_id, {})
            self.db.flush()
            body = self._full_application_view(row)
            self._idempotency_finish(actor, "application_create", key, digest, body, 201, row.public_id)
            self._outbox("prospect.case_changed.v1", "prospect_case", case.public_id, case.version,
                         correlation_id, self._case_view(case))
            return body
        return self._transaction(command)

    def applications(self, actor: Principal, *, status: str | None, cursor: str | None,
                     limit: int) -> dict:
        query = sa.select(Application)
        if actor.account_type == "customer":
            party = self._party_for(actor.subject_id)
            if not party:
                return {"items": [], "next_cursor": None}
            query = query.where(Application.applicant_id == party.id)
        elif actor.account_type == "staff" and actor.staff_id:
            if not actor.is_admin:
                query = query.join(ProspectCase, ProspectCase.id == Application.prospect_case_id).where(
                    ProspectCase.assigned_consultant_staff_id == actor.staff_id)
        else:
            raise action_forbidden()
        if status:
            query = query.where(Application.status == status)
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(sa.tuple_(Application.created_at, Application.id) < decoded)
        rows = list(self.db.scalars(query.order_by(Application.created_at.desc(), Application.id.desc())
                                    .limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        return {"items": [self._full_application_view(row) for row in rows[:limit]],
                "next_cursor": next_cursor}

    def get_application(self, actor: Principal, application_id: UUID) -> dict:
        row = self._application(application_id)
        if not self._application_access(actor, row):
            raise resource_not_found()
        return self._full_application_view(row)

    def update_application(self, actor: Principal, application_id: UUID, data: dict) -> dict:
        self._require_customer_eligible(actor)

        def command() -> dict:
            row = self._application(application_id, lock=True)
            if not self._application_access(actor, row):
                raise resource_not_found()
            self._expect(row, data["version"], "draft", "application_state_conflict")
            for field in ("desired_start_on", "term_months", "occupants", "note"):
                if data.get(field) is not None:
                    setattr(row, field, data[field])
            row.version += 1
            return self._full_application_view(row)
        return self._transaction(command)

    @staticmethod
    def _expect(row, version: int, allowed: str | set[str], code: str) -> None:
        if row.version != version:
            raise version_conflict(row.version)
        states = {allowed} if isinstance(allowed, str) else allowed
        if row.status not in states:
            raise state_conflict(code, row.status, sorted(states))

    def transition_application(self, actor: Principal, application_id: UUID, data: dict,
                               action: str, key: UUID | None, correlation_id: UUID) -> dict:
        transitions = {
            "submit": ({"draft"}, "submitted", "customer"),
            "start-review": ({"submitted"}, "reviewing", "staff"),
            "approve": ({"reviewing"}, "approved", "staff"),
            "reject": ({"reviewing"}, "rejected", "staff"),
            "withdraw": ({"draft", "submitted", "reviewing", "approved"}, "withdrawn", "customer"),
        }
        allowed, target, side = transitions[action]
        if side == "customer":
            self._require_customer_eligible(actor)
        operation = f"application_{action}"

        def command() -> dict:
            digest = None
            if key:
                digest, replay = self._idempotency_start(actor, operation, key, data)
                if replay is not None:
                    return replay
            row = self._application(application_id, lock=True)
            case = self.db.scalar(sa.select(ProspectCase).where(
                ProspectCase.id == row.prospect_case_id).with_for_update())
            permitted = self._customer_owns_case(actor, case) if side == "customer" else self._staff_case_access(actor, case)
            if not permitted:
                raise resource_not_found()
            self._expect(row, data["version"], allowed, "application_state_conflict")
            if action == "withdraw" and row.status == "approved":
                lease = self.db.scalar(sa.select(Lease).where(Lease.application_id == row.id).with_for_update())
                if lease and lease.status != "draft":
                    raise state_conflict("application_state_conflict", row.status,
                                         ["approved with draft lease"])
                if lease:
                    lease.status = "cancelled"
                    lease.cancelled_at = self.now()
                    lease.cancel_reason = "application_withdrawn"
                    lease.version += 1
                    self._outbox("lease.cancelled.v1", "lease", lease.public_id, lease.version,
                                 correlation_id, {"lease_id": str(lease.public_id),
                                                  "reason_code": lease.cancel_reason})
                self._close_case(case, actor.subject_id, "application_withdrawn")
            row.status = target
            row.version += 1
            if target == "submitted":
                row.submitted_at = self.now()
            if target in {"approved", "rejected"}:
                row.decided_at = self.now()
            if target in {"rejected", "withdrawn"}:
                row.closed_at = self.now()
                row.closed_reason = data.get("reason_code") or data.get("reason") or target
            if target == "approved":
                prop = self.db.scalar(sa.select(Property).where(Property.id == row.property_id).with_for_update())
                if prop.status == "marketing":
                    prop.status = "under_offer"
                    if self.cache:
                        self.cache.invalidate_market()
            body = self._full_application_view(row)
            event_type = "application.decided.v1" if target in {"approved", "rejected"} else "application.changed.v1"
            self._outbox(event_type, "application", row.public_id, row.version, correlation_id, body)
            if key:
                self._idempotency_finish(actor, operation, key, digest, body, 200, row.public_id)
            return body
        return self._transaction(command)

    def _close_case(self, case: ProspectCase, actor_subject: UUID | None, reason: str) -> None:
        previous = case.stage
        case.stage = "lost"
        case.status = "closed"
        case.closed_at = self.now()
        case.version += 1
        self._case_event(case, "case_closed", previous, "lost", actor_subject, {"reason": reason})

    @staticmethod
    def _terms_digest(payload: dict) -> str:
        value = json.dumps(jsonable_encoder(payload), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode()
        return "sha256:" + hashlib.sha256(value).hexdigest()

    def create_lease(self, actor: Principal, data: dict, key: UUID, correlation_id: UUID) -> dict:
        if actor.account_type != "staff" or not actor.has("lease:prepare"):
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "lease_create", key, data)
            if replay is not None:
                return replay
            application = self._application(data["application_id"], lock=True)
            if application.status != "approved":
                raise state_conflict("application_state_conflict", application.status, ["approved"])
            case = self.db.get(ProspectCase, application.prospect_case_id)
            if not self._staff_case_access(actor, case):
                raise resource_not_found()
            party = self.db.scalar(sa.select(Party).where(Party.id == application.applicant_id).with_for_update())
            if not party.subject_id or party.id != case.prospect_party_id:
                raise error(409, "application_state_conflict", "Applicant is not bound to the case subject")
            self.identity.require_lease_eligible_customer(party.subject_id)
            prop = self.db.scalar(sa.select(Property).where(Property.id == application.property_id).with_for_update())
            if prop.id != case.property_id:
                raise error(409, "application_state_conflict", "Application property does not match case")
            row = Lease(application_id=application.id, property_id=prop.id,
                        reference=f"L-{self.now():%Y}-{uuid4().hex[:10].upper()}",
                        starts_on=data["starts_on"], ends_on=data["ends_on"],
                        weekly_rent=data["weekly_rent"], currency=data["currency"].upper(),
                        status="draft", offer_expires_at=data["offer_expires_at"], version=1)
            self.db.add(row)
            self.db.flush()
            tenant = LeaseTenant(lease_id=row.id, party_id=party.id, signing_status="pending", version=1)
            document = LeaseDocument(public_id=uuid4(), lease_id=row.id, version=1,
                                     terms_payload=data["terms_payload"],
                                     terms_digest=self._terms_digest(data["terms_payload"]), status="issued",
                                     created_by_subject_id=actor.subject_id)
            self.db.add_all([tenant, document])
            self.db.flush()
            body = self._lease_view(row)
            self._idempotency_finish(actor, "lease_create", key, digest, body, 201, row.public_id)
            return body
        try:
            return self._transaction(command)
        except IntegrityError as exc:
            if "uq_leases_application_id" in str(exc.orig):
                raise error(409, "application_already_has_lease",
                            "Application already has a lease") from exc
            raise

    def _lease_subject(self, lease: Lease) -> tuple[LeaseTenant, Party]:
        tenant = self.db.scalar(sa.select(LeaseTenant).where(LeaseTenant.lease_id == lease.id))
        party = self.db.get(Party, tenant.party_id) if tenant else None
        if not tenant or not party or not party.subject_id:
            raise error(409, "lease_state_conflict", "Lease has no valid tenant")
        return tenant, party

    def _current_document(self, lease: Lease) -> LeaseDocument:
        document = self.db.scalar(sa.select(LeaseDocument).where(
            LeaseDocument.lease_id == lease.id, LeaseDocument.status == "issued")
            .order_by(LeaseDocument.version.desc()).limit(1))
        if not document:
            raise error(409, "lease_state_conflict", "Lease has no current document")
        return document

    def _lease_view(self, row: Lease) -> dict:
        prop = self.db.get(Property, row.property_id)
        tenant, party = self._lease_subject(row)
        document = self._current_document(row)
        return {
            "id": str(row.public_id), "reference": row.reference,
            "application_id": str(self.db.get(Application, row.application_id).public_id),
            "property": {"id": str(prop.public_id), "reference": prop.reference, "address": prop.address},
            "starts_on": row.starts_on, "ends_on": row.ends_on,
            "weekly_rent": str(row.weekly_rent), "currency": row.currency, "status": row.status,
            "document": {"id": str(document.public_id), "version": document.version,
                         "terms_digest": document.terms_digest},
            "tenant_signers": [{"subject_id": str(party.subject_id), "status": tenant.signing_status,
                                "signed_at": tenant.signed_at}],
            "company_signed_at": row.company_signed_at, "offer_expires_at": row.offer_expires_at,
            "executed_at": row.executed_at, "version": row.version,
        }

    def _lease_access(self, actor: Principal, lease: Lease) -> bool:
        tenant, party = self._lease_subject(lease)
        if actor.account_type == "customer":
            return party.subject_id == actor.subject_id
        prop = self.db.get(Property, lease.property_id)
        case = self.db.get(ProspectCase, self.db.get(Application, lease.application_id).prospect_case_id)
        return self._staff_case_access(actor, case) or self._staff_property_access(actor, prop)

    def leases(self, actor: Principal, *, status: str | None, property_id: UUID | None,
               cursor: str | None, limit: int) -> dict:
        query = sa.select(Lease)
        if actor.account_type == "customer":
            party = self._party_for(actor.subject_id)
            if not party:
                return {"items": [], "next_cursor": None}
            query = query.join(LeaseTenant, LeaseTenant.lease_id == Lease.id).where(
                LeaseTenant.party_id == party.id)
        elif actor.account_type == "staff" and actor.staff_id:
            if not actor.is_admin and not actor.has("property:read_market"):
                now = self.now()
                query = query.join(Property, Property.id == Lease.property_id).where(sa.or_(
                    sa.exists(sa.select(StaffPropertyScope.id).where(
                        StaffPropertyScope.staff_id == actor.staff_id,
                        StaffPropertyScope.property_id == Lease.property_id,
                        StaffPropertyScope.valid_from <= now,
                        sa.or_(StaffPropertyScope.valid_until.is_(None), StaffPropertyScope.valid_until > now))),
                    sa.exists(sa.select(StaffBuildingScope.id).where(
                        StaffBuildingScope.staff_id == actor.staff_id,
                        StaffBuildingScope.building_id == Property.building_id,
                        StaffBuildingScope.valid_from <= now,
                        sa.or_(StaffBuildingScope.valid_until.is_(None), StaffBuildingScope.valid_until > now))),
                    sa.exists(sa.select(ProspectCase.id).join(
                        Application, Application.prospect_case_id == ProspectCase.id).where(
                        Application.id == Lease.application_id,
                        ProspectCase.assigned_consultant_staff_id == actor.staff_id)),
                ))
        else:
            raise action_forbidden()
        if status:
            query = query.where(Lease.status == status)
        if property_id:
            query = query.join(Property, Property.id == Lease.property_id).where(Property.public_id == property_id)
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(sa.tuple_(Lease.created_at, Lease.id) < decoded)
        rows = list(self.db.scalars(query.order_by(Lease.created_at.desc(), Lease.id.desc()).limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        return {"items": [self._lease_view(row) for row in rows[:limit]], "next_cursor": next_cursor}

    def get_lease(self, actor: Principal, lease_id: UUID) -> dict:
        lease = self._lease(lease_id)
        if not self._lease_access(actor, lease):
            raise resource_not_found("lease_access_required")
        return self._lease_view(lease)

    def get_document(self, actor: Principal, lease_id: UUID) -> dict:
        lease = self._lease(lease_id)
        if not self._lease_access(actor, lease):
            raise resource_not_found("lease_access_required")
        document = self._current_document(lease)
        return {"id": str(document.public_id), "lease_id": str(lease.public_id),
                "version": document.version, "terms_payload": document.terms_payload,
                "terms_digest": document.terms_digest, "status": document.status,
                "created_at": document.created_at}

    def update_lease(self, actor: Principal, lease_id: UUID, data: dict) -> dict:
        if actor.account_type != "staff" or not actor.has("lease:prepare"):
            raise action_forbidden()

        def command() -> dict:
            lease = self._lease(lease_id, lock=True)
            if not self._lease_access(actor, lease):
                raise resource_not_found("lease_access_required")
            self._expect(lease, data["version"], "draft", "lease_state_conflict")
            for field in ("starts_on", "ends_on", "weekly_rent", "currency", "offer_expires_at"):
                if data.get(field) is not None:
                    setattr(lease, field, data[field])
            if lease.ends_on < lease.starts_on:
                raise error(422, "validation_failed", "Lease dates are invalid")
            if data.get("terms_payload") is not None:
                current = self._current_document(lease)
                current.status = "superseded"
                self.db.add(LeaseDocument(public_id=uuid4(), lease_id=lease.id,
                                          version=current.version + 1,
                                          terms_payload=data["terms_payload"],
                                          terms_digest=self._terms_digest(data["terms_payload"]),
                                          status="issued", created_by_subject_id=actor.subject_id))
            lease.version += 1
            self.db.flush()
            return self._lease_view(lease)
        return self._transaction(command)

    def send_for_signature(self, actor: Principal, lease_id: UUID, data: dict, key: UUID,
                           correlation_id: UUID) -> dict:
        if actor.account_type != "staff" or not actor.has("lease:prepare"):
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "lease_send_for_signature", key, data)
            if replay is not None:
                return replay
            lease = self._lease(lease_id, lock=True)
            if not self._lease_access(actor, lease):
                raise resource_not_found("lease_access_required")
            self._expect(lease, data["version"], "draft", "lease_state_conflict")
            tenant, party = self._lease_subject(lease)
            self.identity.require_lease_eligible_customer(party.subject_id)
            prop = self.db.scalar(sa.select(Property).where(Property.id == lease.property_id).with_for_update())
            document = self._current_document(lease)
            if document.public_id != data["lease_document_id"]:
                raise error(409, "lease_terms_changed", "Lease document has changed",
                            current_document_id=str(document.public_id),
                            current_terms_digest=document.terms_digest)
            if lease.offer_expires_at is None or lease.offer_expires_at <= self.now():
                raise error(409, "lease_offer_expired", "Lease offer has expired",
                            offer_expires_at=lease.offer_expires_at)
            self.db.add(CustomerLeaseSlot(customer_subject_id=party.subject_id, lease_id=lease.id,
                                          status="pending_signature", reserved_at=self.now(), version=1))
            lease.status = "pending_signature"
            lease.version += 1
            if prop.status == "marketing":
                prop.status = "under_offer"
                if self.cache:
                    self.cache.invalidate_market()
            self.db.flush()
            body = self._lease_view(lease)
            self._idempotency_finish(actor, "lease_send_for_signature", key, digest, body, 200,
                                     lease.public_id)
            self._outbox("property.status_changed.v1", "property", prop.public_id, lease.version,
                         correlation_id, {"property_id": str(prop.public_id), "status": prop.status,
                                          "visibility": prop.listing_visibility})
            return body
        try:
            return self._transaction(command)
        except IntegrityError as exc:
            name = str(exc.orig)
            if "customer_lease_slots" in name:
                raise error(409, "customer_already_has_lease",
                            "Customer already has a current lease") from exc
            if "ex_property_active_date_overlap" in name:
                raise error(409, "lease_date_overlap", "Lease dates overlap another current lease") from exc
            raise

    def sign_lease(self, actor: Principal, lease_id: UUID, data: dict, key: UUID,
                   correlation_id: UUID, *, side: str) -> dict:
        if side == "tenant":
            self._require_customer_eligible(actor)
        elif actor.account_type != "staff" or not actor.has("lease:execute"):
            raise action_forbidden()
        operation = f"lease_{side}_signature"

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, operation, key, data)
            if replay is not None:
                return replay
            lease = self._lease(lease_id, lock=True)
            tenant, party = self._lease_subject(lease)
            if side == "tenant" and party.subject_id != actor.subject_id:
                raise resource_not_found("lease_access_required")
            if side == "company" and not self._lease_access(actor, lease):
                raise resource_not_found("lease_access_required")
            self._expect(lease, data["version"], "pending_signature", "lease_state_conflict")
            slot = self.db.scalar(sa.select(CustomerLeaseSlot).where(
                CustomerLeaseSlot.customer_subject_id == party.subject_id).with_for_update())
            if not slot or slot.lease_id != lease.id:
                raise error(409, "lease_slot_mismatch", "Lease reservation does not match")
            document = self._current_document(lease)
            if document.public_id != data["lease_document_id"] or document.terms_digest != data["terms_digest"]:
                raise error(409, "lease_terms_changed", "Lease document has changed",
                            current_document_id=str(document.public_id),
                            current_terms_digest=document.terms_digest)
            timestamp = self.now()
            if side == "tenant":
                tenant.signing_status = "signed"
                tenant.signed_at = timestamp
                tenant.version += 1
                lease.tenant_signed_at = timestamp
            else:
                lease.company_signed_at = timestamp
            self.db.add(LeaseSignatureEvent(
                lease_id=lease.id, lease_document_id=document.id,
                signer_subject_id=actor.subject_id if side == "tenant" else None,
                signer_staff_id=actor.staff_id if side == "company" else None,
                side=side, terms_digest=document.terms_digest,
                ip_hash=data.get("ip_hash"), user_agent_hash=data.get("user_agent_hash"),
                occurred_at=timestamp, correlation_id=correlation_id,
            ))
            lease.version += 1
            self.db.flush()
            body = self._lease_view(lease)
            self._idempotency_finish(actor, operation, key, digest, body, 200, lease.public_id)
            return body
        return self._transaction(command)

    def execute_lease(self, actor: Principal, lease_id: UUID, data: dict, key: UUID,
                      correlation_id: UUID) -> dict:
        if actor.account_type != "staff" or not actor.has("lease:execute"):
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "lease_execute", key, data)
            if replay is not None:
                return replay
            lease = self._lease(lease_id, lock=True)
            if not self._lease_access(actor, lease):
                raise resource_not_found("lease_access_required")
            self._expect(lease, data["version"], "pending_signature", "lease_state_conflict")
            tenant, party = self._lease_subject(lease)
            slot = self.db.scalar(sa.select(CustomerLeaseSlot).where(
                CustomerLeaseSlot.customer_subject_id == party.subject_id).with_for_update())
            prop = self.db.scalar(sa.select(Property).where(Property.id == lease.property_id).with_for_update())
            if not slot or slot.lease_id != lease.id:
                raise error(409, "lease_slot_mismatch", "Lease reservation does not match")
            if tenant.signing_status != "signed" or not lease.tenant_signed_at or not lease.company_signed_at:
                missing = []
                if tenant.signing_status != "signed":
                    missing.append("tenant")
                if not lease.company_signed_at:
                    missing.append("company")
                raise error(409, "lease_signature_incomplete", "Lease signatures are incomplete",
                            missing_sides=missing)
            if lease.offer_expires_at and lease.offer_expires_at <= self.now():
                raise error(409, "lease_offer_expired", "Lease offer has expired",
                            offer_expires_at=lease.offer_expires_at)
            executed_at = self.now()
            lease.status = "executed"
            lease.executed_at = executed_at
            lease.version += 1
            slot.status = "executed"
            slot.version += 1
            winner = self.db.scalar(sa.select(Application).where(
                Application.id == lease.application_id).with_for_update())
            winner.closed_reason = "lease_executed"
            winner.closed_at = executed_at
            winner.winning_lease_id = lease.id
            winner.version += 1
            winning_case = self.db.scalar(sa.select(ProspectCase).where(
                ProspectCase.id == winner.prospect_case_id).with_for_update())
            old_stage = winning_case.stage
            winning_case.stage = "converted"
            winning_case.status = "closed"
            winning_case.converted_lease_id = lease.id
            winning_case.converted_at = executed_at
            winning_case.closed_at = executed_at
            winning_case.version += 1
            self._case_event(winning_case, "lease_converted", old_stage, "converted",
                             actor.subject_id, {"lease_id": str(lease.public_id)})
            self._invalidate_other_applications(party, winner, lease, actor, correlation_id)
            prop.status = "occupied"
            if self.cache:
                self.cache.invalidate_market()
            body = self._lease_view(lease)
            self._outbox("lease.executed.v1", "lease", lease.public_id, lease.version,
                         correlation_id, {"lease_id": str(lease.public_id),
                                          "property_id": str(prop.public_id),
                                          "customer_subject_id": str(party.subject_id),
                                          "starts_on": lease.starts_on, "ends_on": lease.ends_on,
                                          "lease_version": lease.version})
            customer_version = self._next_customer_version(party.subject_id)
            self._outbox("customer.tenancy_status_changed.v1", "customer", party.subject_id,
                         customer_version, correlation_id,
                         {"customer_subject_id": str(party.subject_id),
                          "lease_id": str(lease.public_id), "to_status": "tenant",
                          "aggregate_version": customer_version, "occurred_at": executed_at})
            self._outbox("property.status_changed.v1", "property", prop.public_id, lease.version,
                         correlation_id, {"property_id": str(prop.public_id), "status": prop.status,
                                          "visibility": prop.listing_visibility})
            self._idempotency_finish(actor, "lease_execute", key, digest, body, 200, lease.public_id)
            return body

        try:
            return self._transaction(command)
        except IntegrityError as exc:
            if "ex_property_active_date_overlap" in str(exc.orig):
                raise error(409, "lease_date_overlap", "Lease dates overlap another current lease") from exc
            raise

    def _invalidate_other_applications(self, party: Party, winner: Application, winning_lease: Lease,
                                       actor: Principal, correlation_id: UUID) -> None:
        losers = list(self.db.scalars(sa.select(Application).where(
            Application.applicant_id == party.id, Application.id != winner.id,
            Application.status.in_({"draft", "submitted", "reviewing", "approved"}))
            .order_by(Application.id).with_for_update()))
        case_ids = sorted({row.prospect_case_id for row in losers})
        cases = {row.id: row for row in self.db.scalars(sa.select(ProspectCase).where(
            ProspectCase.id.in_(case_ids)).order_by(ProspectCase.id).with_for_update())} if case_ids else {}
        for application in losers:
            previous = application.status
            application.status = "expired" if previous == "approved" else "ineligible"
            application.closed_reason = "another_lease_executed"
            application.closed_at = self.now()
            application.winning_lease_id = winning_lease.id
            application.version += 1
            draft = self.db.scalar(sa.select(Lease).where(
                Lease.application_id == application.id, Lease.status == "draft").with_for_update())
            if draft:
                draft.status = "cancelled"
                draft.cancelled_at = self.now()
                draft.cancel_reason = "another_lease_executed"
                draft.version += 1
                self._outbox("lease.cancelled.v1", "lease", draft.public_id, draft.version,
                             correlation_id, {"lease_id": str(draft.public_id),
                                              "customer_subject_id": str(party.subject_id),
                                              "reason_code": "another_lease_executed"})
            case = cases[application.prospect_case_id]
            if case.status != "closed":
                self._close_case(case, actor.subject_id, "another_lease_executed")
            self._outbox("application.invalidated.v1", "application", application.public_id,
                         application.version, correlation_id,
                         {"application_id": str(application.public_id),
                          "customer_subject_id": str(party.subject_id),
                          "previous_status": previous, "status": application.status,
                          "closed_reason": application.closed_reason,
                          "closed_at": application.closed_at,
                          "winning_lease_id": str(winning_lease.public_id),
                          "assigned_staff_id": str(case.assigned_consultant_staff_id)
                          if case.assigned_consultant_staff_id else None,
                          "version": application.version})

    def cancel_or_expire(self, actor: Principal, lease_id: UUID, data: dict, key: UUID,
                         correlation_id: UUID, *, action: str) -> dict:
        if action == "expire":
            if not actor.has("lease:lifecycle") and not actor.is_admin:
                raise action_forbidden()
        elif actor.account_type != "staff" or not (actor.has("lease:prepare") or actor.has("lease:execute")):
            raise action_forbidden()
        operation = f"lease_{action}"

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, operation, key, data)
            if replay is not None:
                return replay
            lease = self._lease(lease_id, lock=True)
            allowed = {"draft", "pending_signature"} if action == "cancel" else {"pending_signature"}
            self._expect(lease, data["version"], allowed, "lease_state_conflict")
            if action == "expire" and (not lease.offer_expires_at or data["as_of"] < lease.offer_expires_at):
                raise error(409, "lease_offer_expired", "Lease is not due to expire",
                            offer_expires_at=lease.offer_expires_at)
            tenant, party = self._lease_subject(lease)
            prop = self.db.scalar(sa.select(Property).where(Property.id == lease.property_id).with_for_update())
            slot = self.db.scalar(sa.select(CustomerLeaseSlot).where(
                CustomerLeaseSlot.customer_subject_id == party.subject_id).with_for_update())
            if slot and slot.lease_id == lease.id:
                self.db.delete(slot)
            lease.status = "expired" if action == "expire" else "cancelled"
            lease.cancelled_at = self.now()
            lease.cancel_reason = "offer_expired" if action == "expire" else data["reason_code"]
            lease.version += 1
            application = self.db.scalar(sa.select(Application).where(
                Application.id == lease.application_id).with_for_update())
            application.status = "expired"
            application.closed_reason = lease.cancel_reason
            application.closed_at = self.now()
            application.version += 1
            case = self.db.scalar(sa.select(ProspectCase).where(
                ProspectCase.id == application.prospect_case_id).with_for_update())
            self._close_case(case, actor.subject_id, lease.cancel_reason)
            active_process = self.db.scalar(sa.select(Application.id).where(
                Application.property_id == prop.id,
                Application.status.in_({"submitted", "reviewing", "approved"})).limit(1))
            current_lease = self.db.scalar(sa.select(Lease.id).where(
                Lease.property_id == prop.id, Lease.status.in_(ACTIVE_LEASE_STATES)).limit(1))
            prop.status = "under_offer" if active_process or current_lease else "marketing"
            if self.cache:
                self.cache.invalidate_market()
            self._outbox(f"lease.{lease.status}.v1", "lease", lease.public_id, lease.version,
                         correlation_id, {"lease_id": str(lease.public_id),
                                          "property_id": str(prop.public_id),
                                          "customer_subject_id": str(party.subject_id),
                                          "reason_code": lease.cancel_reason,
                                          f"{lease.status}_at": lease.cancelled_at})
            body = self._lease_view(lease)
            self._idempotency_finish(actor, operation, key, digest, body, 200, lease.public_id)
            return body
        return self._transaction(command)

    def activate(self, actor: Principal, lease_id: UUID, data: dict, key: UUID,
                 correlation_id: UUID) -> dict:
        if not actor.has("lease:lifecycle") and not actor.is_admin:
            raise action_forbidden()

        def command() -> dict:
            digest, replay = self._idempotency_start(actor, "lease_activate", key, data)
            if replay is not None:
                return replay
            lease = self._lease(lease_id, lock=True)
            self._expect(lease, data["version"], "executed", "lease_state_conflict")
            prop = self.db.scalar(sa.select(Property).where(Property.id == lease.property_id).with_for_update())
            building = self.db.get(Building, prop.building_id) if prop.building_id else None
            if data["as_of"].date() < lease.starts_on:
                raise error(409, "lease_activation_not_due", "Lease is not due to activate",
                            effective_on=lease.starts_on,
                            building_timezone=building.timezone if building else "UTC")
            tenant, party = self._lease_subject(lease)
            slot = self.db.scalar(sa.select(CustomerLeaseSlot).where(
                CustomerLeaseSlot.customer_subject_id == party.subject_id).with_for_update())
            if not slot or slot.lease_id != lease.id:
                raise error(409, "lease_slot_mismatch", "Lease reservation does not match")
            lease.status = "active"
            lease.version += 1
            slot.status = "active"
            slot.version += 1
            self._outbox("lease.activated.v1", "lease", lease.public_id, lease.version,
                         correlation_id, {"lease_id": str(lease.public_id),
                                          "property_id": str(prop.public_id),
                                          "customer_subject_id": str(party.subject_id),
                                          "starts_on": lease.starts_on})
            body = self._lease_view(lease)
            self._idempotency_finish(actor, "lease_activate", key, digest, body, 200, lease.public_id)
            return body
        return self._transaction(command)

    def property_authorization(self, actor: Principal, data: dict) -> dict:
        prop = self._property(data["property_id"])
        allowed = False
        active_lease_id = None
        if actor.account_type == "staff":
            allowed = self._staff_property_access(actor, prop)
        elif actor.subject_id == data["subject_id"]:
            lease = self.db.scalar(sa.select(Lease).join(LeaseTenant, LeaseTenant.lease_id == Lease.id)
                                   .join(Party, Party.id == LeaseTenant.party_id).where(
                Party.subject_id == actor.subject_id, Lease.property_id == prop.id,
                Lease.status == "active"))
            allowed = lease is not None
            active_lease_id = str(lease.public_id) if lease else None
        return {"allowed": allowed, "property_id": str(prop.public_id),
                "active_lease_id": active_lease_id,
                "property_version": int((prop.updated_at or prop.created_at).timestamp())}

    def lease_authorization(self, actor: Principal, data: dict) -> dict:
        lease = self._lease(data["lease_id"])
        if data.get("property_id"):
            prop = self.db.get(Property, lease.property_id)
            if prop.public_id != data["property_id"]:
                return {"allowed": False}
        allowed = actor.subject_id == data["subject_id"] and self._lease_access(actor, lease)
        tenant, _ = self._lease_subject(lease)
        return {"allowed": allowed, "lease_id": str(lease.public_id),
                "property_id": str(self.db.get(Property, lease.property_id).public_id),
                "status": lease.status, "lease_version": lease.version,
                "relationship_version": tenant.version}

    def invoices(self, actor: Principal, lease_id: UUID, status: str | None,
                 cursor: str | None, limit: int) -> dict:
        lease = self._lease(lease_id)
        if not self._lease_access(actor, lease) or lease.status not in {
            "executed", "active", "ended", "terminated"
        }:
            raise resource_not_found("lease_access_required")
        query = sa.select(RentInvoice).where(RentInvoice.lease_id == lease.id)
        if status:
            query = query.where(RentInvoice.status == status)
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(sa.tuple_(RentInvoice.created_at, RentInvoice.id) < decoded)
        rows = list(self.db.scalars(query.order_by(RentInvoice.created_at.desc(), RentInvoice.id.desc())
                                    .limit(limit + 1)))
        next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
        total = sum((row.amount for row in rows[:limit]), Decimal("0"))
        return {"items": [{"reference": row.reference, "due_on": row.due_on,
                           "period_start": row.period_start, "period_end": row.period_end,
                           "amount": str(row.amount), "currency": row.currency,
                           "status": row.status} for row in rows[:limit]],
                "totals": {"amount": str(total), "currency": lease.currency},
                "next_cursor": next_cursor}
