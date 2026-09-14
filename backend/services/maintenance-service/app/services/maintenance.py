from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.clients.dependencies import DependencyClient
from app.core.config import Settings
from app.core.errors import error, forbidden, not_found, version_conflict
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.principal import Principal
from app.mappers.orders import event_view, order_view
from app.models.tables import (
    IdempotencyRecord,
    MaintenanceEvent,
    MaintenanceOrder,
    OutboxEvent,
    SubjectDeletionRecord,
)

OPEN_STATES = {"open", "assigned", "in_progress", "blocked"}
TRANSITIONS = {
    "open": {"cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "completed", "cancelled"},
    "blocked": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class MaintenanceService:
    def __init__(
        self, db: Session, dependencies: DependencyClient, settings: Settings
    ) -> None:
        self.db, self.dependencies, self.settings = db, dependencies, settings

    @staticmethod
    def _hash(data: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                data, sort_keys=True, separators=(",", ":"), default=str
            ).encode()
        ).hexdigest()

    def _transaction(self, callback):
        try:
            result = callback()
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def _idempotency_start(
        self, actor: Principal, operation: str, key: UUID, data: dict
    ):
        lock_key = f"{actor.subject_id}:{operation}:{key}"
        self.db.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        digest = self._hash(data)
        record = self.db.scalar(
            sa.select(IdempotencyRecord)
            .where(
                IdempotencyRecord.actor_subject_id == actor.subject_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == key,
            )
            .with_for_update()
        )
        if record:
            if record.request_hash != digest:
                raise error(
                    409,
                    "idempotency_conflict",
                    "Idempotency key was used with another request",
                    operation=operation,
                )
            if record.response_body is not None:
                return digest, record.response_body
        else:
            self.db.add(
                IdempotencyRecord(
                    actor_subject_id=actor.subject_id,
                    operation=operation,
                    idempotency_key=key,
                    request_hash=digest,
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=self.settings.idempotency_ttl_hours),
                )
            )
            self.db.flush()
        return digest, None

    def _idempotency_finish(
        self,
        actor: Principal,
        operation: str,
        key: UUID,
        digest: str,
        body: dict,
        status: int,
        resource_id: UUID | None = None,
    ) -> None:
        record = self.db.scalar(
            sa.select(IdempotencyRecord)
            .where(
                IdempotencyRecord.actor_subject_id == actor.subject_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == key,
            )
            .with_for_update()
        )
        record.request_hash, record.response_body, record.response_status = (
            digest,
            body,
            status,
        )
        record.resource_id = resource_id

    def _order(self, public_id: UUID, lock: bool = False) -> MaintenanceOrder:
        query = sa.select(MaintenanceOrder).where(
            MaintenanceOrder.public_id == public_id
        )
        row = self.db.scalar(query.with_for_update() if lock else query)
        if not row:
            raise not_found()
        return row

    def _events(self, order: MaintenanceOrder) -> list[MaintenanceEvent]:
        return list(
            self.db.scalars(
                sa.select(MaintenanceEvent)
                .where(MaintenanceEvent.order_id == order.id)
                .order_by(MaintenanceEvent.sequence_no)
            )
        )

    def _append(
        self,
        order: MaintenanceOrder,
        actor: Principal | None,
        event_type: str,
        visibility: str = "public",
        message: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        client_message_id: UUID | None = None,
        details: dict | None = None,
    ) -> MaintenanceEvent:
        event = MaintenanceEvent(
            order_id=order.id,
            sequence_no=order.next_event_sequence,
            actor_staff_id=actor.staff_id if actor else None,
            actor_subject_id=actor.subject_id if actor else None,
            actor_type=actor.account_type if actor else "system",
            event_type=event_type,
            visibility=visibility,
            message=message,
            from_status=from_status,
            to_status=to_status,
            client_message_id=client_message_id,
            details=details or {},
        )
        order.next_event_sequence += 1
        self.db.add(event)
        return event

    def _outbox(
        self,
        event_type: str,
        order: MaintenanceOrder,
        correlation_id: UUID,
        payload: dict,
    ) -> None:
        self.db.add(
            OutboxEvent(
                event_id=uuid4(),
                event_type=event_type,
                schema_version=1,
                aggregate_type="maintenance_order",
                aggregate_id=order.public_id,
                aggregate_version=order.version,
                correlation_id=correlation_id,
                payload=payload,
                status="pending",
                attempts=0,
                available_at=datetime.now(UTC),
            )
        )

    def _manager_access(
        self, actor: Principal, order: MaintenanceOrder, action: str
    ) -> bool:
        if actor.is_admin:
            return True
        permission = (
            "maintenance:assign_assigned"
            if action == "assign"
            else "maintenance:update_assigned"
        )
        return (
            actor.account_type == "staff"
            and actor.staff_id is not None
            and actor.has(permission)
            and self.dependencies.property_access(
                actor, order.property_id, f"maintenance:{action}_assigned"
            )
        )

    def _visible(self, actor: Principal, order: MaintenanceOrder) -> bool:
        if actor.account_type == "customer":
            return (
                actor.has("maintenance:self:create")
                and order.reported_by_subject_id == actor.subject_id
            )
        if actor.is_admin:
            return True
        if actor.staff_id and actor.has("work_order:read_assigned"):
            return order.assigned_staff_id == actor.staff_id
        if actor.has("maintenance:assign_assigned") or actor.has(
            "maintenance:update_assigned"
        ):
            return self.dependencies.property_access(
                actor, order.property_id, "maintenance:read_assigned"
            )
        return False

    def create(
        self, actor: Principal, data: dict, key: UUID, correlation_id: UUID
    ) -> dict:
        if (
            actor.account_type != "customer"
            or actor.customer_status != "tenant"
            or not actor.has("maintenance:self:create")
        ):
            raise forbidden()
        if not data.get("lease_id"):
            raise error(
                422,
                "validation_failed",
                "lease_id is required for a tenant order",
                fields=[{"field": "lease_id", "reason": "required"}],
            )

        def command():
            digest, replay = self._idempotency_start(actor, "order_create", key, data)
            if replay is not None:
                return replay
            first = self.dependencies.lease_access(
                actor, data["lease_id"], data["property_id"]
            )
            if not first.get("allowed") or first.get("status") != "active":
                raise not_found()
            second = self.dependencies.lease_access(
                actor, data["lease_id"], data["property_id"]
            )
            if (
                not second.get("allowed")
                or second.get("status") != "active"
                or second.get("lease_version") != first.get("lease_version")
                or second.get("relationship_version")
                != first.get("relationship_version")
            ):
                raise not_found()
            order = MaintenanceOrder(
                public_id=uuid4(),
                property_id=data["property_id"],
                lease_id=data["lease_id"],
                reference=f"WO-{uuid4().hex[:12].upper()}",
                summary=data["summary"],
                description=data.get("description"),
                priority=data["priority"],
                status="open",
                reported_by_subject_id=actor.subject_id,
                version=1,
                next_event_sequence=1,
            )
            self.db.add(order)
            self.db.flush()
            self._append(order, actor, "reported", message="Maintenance issue reported")
            self._outbox(
                "maintenance.order_created.v1",
                order,
                correlation_id,
                {
                    "order_id": str(order.public_id),
                    "property_id": str(order.property_id),
                    "lease_id": str(order.lease_id),
                    "reported_by_subject_id": str(actor.subject_id),
                    "priority": order.priority,
                    "version": order.version,
                },
            )
            self.db.flush()
            body = order_view(order, self._events(order), "tenant")
            self._idempotency_finish(
                actor, "order_create", key, digest, body, 201, order.public_id
            )
            return body

        return self._transaction(command)

    def get(self, actor: Principal, order_id: UUID) -> dict:
        order = self._order(order_id)
        if not self._visible(actor, order):
            raise not_found()
        projection = (
            "tenant"
            if actor.account_type == "customer"
            else "admin"
            if actor.is_admin
            else "staff"
        )
        return order_view(order, self._events(order), projection)

    def list(
        self,
        actor: Principal,
        property_id: UUID | None,
        status: str | None,
        assignee_id: UUID | None,
        priority: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        query = sa.select(MaintenanceOrder)
        scope_filter = False
        if status:
            query = query.where(MaintenanceOrder.status == status)
        if priority:
            query = query.where(MaintenanceOrder.priority == priority)
        if property_id:
            query = query.where(MaintenanceOrder.property_id == property_id)
        if actor.account_type == "customer":
            if not actor.has("maintenance:self:create"):
                raise not_found()
            query = query.where(
                MaintenanceOrder.reported_by_subject_id == actor.subject_id
            )
        elif actor.is_admin:
            if assignee_id:
                query = query.where(MaintenanceOrder.assigned_staff_id == assignee_id)
        elif actor.staff_id and actor.has("work_order:read_assigned"):
            query = query.where(MaintenanceOrder.assigned_staff_id == actor.staff_id)
        elif actor.has("maintenance:assign_assigned") or actor.has(
            "maintenance:update_assigned"
        ):
            if property_id and not self.dependencies.property_access(
                actor, property_id, "maintenance:read_assigned"
            ):
                raise not_found()
            scope_filter = property_id is None
        else:
            raise not_found()
        decoded = decode_cursor(cursor)
        if decoded:
            query = query.where(
                sa.tuple_(MaintenanceOrder.created_at, MaintenanceOrder.id) < decoded
            )
        scan_limit = 201 if scope_filter else limit + 1
        rows = list(
            self.db.scalars(
                query.order_by(
                    MaintenanceOrder.created_at.desc(), MaintenanceOrder.id.desc()
                ).limit(scan_limit)
            )
        )
        next_cursor = None
        if scope_filter:
            allowed: dict[UUID, bool] = {}
            visible = []
            last_scanned = None
            last_index = -1
            for index, row in enumerate(rows):
                last_index = index
                last_scanned = row
                if row.property_id not in allowed:
                    allowed[row.property_id] = self.dependencies.property_access(
                        actor, row.property_id, "maintenance:read_assigned"
                    )
                if allowed[row.property_id]:
                    visible.append(row)
                    if len(visible) == limit:
                        break
            has_more = bool(
                last_scanned and (last_index < len(rows) - 1 or len(rows) == scan_limit)
            )
            rows = visible
            if has_more:
                next_cursor = encode_cursor(last_scanned.created_at, last_scanned.id)
        else:
            if len(rows) > limit:
                rows = rows[:limit]
                next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)
        return {"items": [order_view(row) for row in rows], "next_cursor": next_cursor}

    def batch(self, actor: Principal, order_ids: list[UUID]) -> list[dict]:
        rows = list(
            self.db.scalars(
                sa.select(MaintenanceOrder).where(
                    MaintenanceOrder.public_id.in_(order_ids)
                )
            )
        )
        by_id = {row.public_id: row for row in rows}
        allowed_properties: dict[UUID, bool] = {}
        result = []
        for public_id in order_ids:
            order = by_id.get(public_id)
            if not order:
                continue
            if (
                actor.account_type == "staff"
                and not actor.is_admin
                and (
                    actor.has("maintenance:assign_assigned")
                    or actor.has("maintenance:update_assigned")
                )
            ):
                if order.property_id not in allowed_properties:
                    allowed_properties[order.property_id] = (
                        self.dependencies.property_access(
                            actor, order.property_id, "maintenance:read_assigned"
                        )
                    )
                visible = allowed_properties[order.property_id]
            else:
                visible = self._visible(actor, order)
            if visible:
                result.append(order_view(order))
        return result

    def work_context(self, actor: Principal, order_id: UUID) -> dict:
        order = self._order(order_id)
        if not (
            actor.account_type == "staff"
            and actor.staff_id == order.assigned_staff_id
            and actor.has("work_order:read_assigned")
            and actor.has("property:read_work_context")
        ):
            raise not_found()
        view = order_view(order, self._events(order), "staff")
        return {
            "order": view,
            "property_id": str(order.property_id),
            "lease_id": str(order.lease_id) if order.lease_id else None,
        }

    def update(
        self,
        actor: Principal,
        order_id: UUID,
        data: dict,
        key: UUID,
        correlation_id: UUID,
    ) -> dict:
        def command():
            digest, replay = self._idempotency_start(
                actor, "order_update", key, {"order_id": order_id, **data}
            )
            if replay is not None:
                return replay
            order = self._order(order_id, lock=True)
            reporter = (
                actor.account_type == "customer"
                and actor.has("maintenance:self:create")
                and order.reported_by_subject_id == actor.subject_id
            )
            manager = (
                self._manager_access(actor, order, "update")
                if actor.account_type == "staff"
                else False
            )
            if not reporter and not manager:
                raise not_found()
            if order.status != "open":
                raise error(
                    409,
                    "order_state_conflict",
                    "Order cannot be edited",
                    current_state=order.status,
                    allowed_states=["open"],
                )
            if order.version != data["version"]:
                raise version_conflict(order.version)
            for field in ("summary", "description", "priority"):
                if data.get(field) is not None:
                    setattr(order, field, data[field])
            order.version += 1
            self._append(
                order,
                actor,
                "updated",
                visibility="public",
                message="Order details updated",
            )
            self._outbox(
                "maintenance.order_changed.v1",
                order,
                correlation_id,
                {"order_id": str(order.public_id), "version": order.version},
            )
            self.db.flush()
            body = order_view(
                order, self._events(order), "tenant" if reporter else "staff"
            )
            self._idempotency_finish(
                actor, "order_update", key, digest, body, 200, order.public_id
            )
            return body

        return self._transaction(command)

    def assign(
        self,
        actor: Principal,
        order_id: UUID,
        data: dict,
        key: UUID,
        correlation_id: UUID,
    ) -> dict:
        def command():
            digest, replay = self._idempotency_start(
                actor, "order_assign", key, {"order_id": order_id, **data}
            )
            if replay is not None:
                return replay
            order = self._order(order_id, lock=True)
            if not self._manager_access(actor, order, "assign"):
                raise not_found()
            if order.status not in {"open", "assigned"}:
                raise error(
                    409,
                    "order_state_conflict",
                    "Order cannot be assigned",
                    current_state=order.status,
                    allowed_states=["open", "assigned"],
                )
            if order.version != data["version"]:
                raise version_conflict(order.version)
            self.dependencies.require_active_maintainer(data["assigned_staff_id"])
            previous, from_status = order.assigned_staff_id, order.status
            order.assigned_staff_id, order.assigned_by_staff_id = (
                data["assigned_staff_id"],
                actor.staff_id,
            )
            order.assigned_at, order.status, order.version = (
                datetime.now(UTC),
                "assigned",
                order.version + 1,
            )
            self._append(
                order,
                actor,
                "reassigned" if previous else "assigned",
                message=data.get("note") or "Order assigned",
                from_status=from_status,
                to_status="assigned",
                details={
                    "previous_assignee_id": str(previous) if previous else None,
                    "assigned_staff_id": str(order.assigned_staff_id),
                },
            )
            self._outbox(
                "maintenance.order_assigned.v1",
                order,
                correlation_id,
                {
                    "order_id": str(order.public_id),
                    "assigned_staff_id": str(order.assigned_staff_id),
                    "assigned_by_staff_id": str(actor.staff_id),
                    "version": order.version,
                },
            )
            self.db.flush()
            body = order_view(order, self._events(order))
            self._idempotency_finish(
                actor, "order_assign", key, digest, body, 200, order.public_id
            )
            return body

        return self._transaction(command)

    def transition(
        self,
        actor: Principal,
        order_id: UUID,
        data: dict,
        key: UUID,
        correlation_id: UUID,
    ) -> dict:
        def command():
            digest, replay = self._idempotency_start(
                actor, "order_transition", key, {"order_id": order_id, **data}
            )
            if replay is not None:
                return replay
            order = self._order(order_id, lock=True)
            target = data["to_status"]
            reporter_cancel = (
                actor.account_type == "customer"
                and actor.has("maintenance:self:create")
                and order.reported_by_subject_id == actor.subject_id
                and order.status == "open"
                and target == "cancelled"
            )
            maintainer = (
                actor.account_type == "staff"
                and actor.staff_id == order.assigned_staff_id
                and actor.has("work_order:update_assigned")
            )
            manager = (
                self._manager_access(actor, order, "update")
                if actor.account_type == "staff"
                else False
            )
            if not (reporter_cancel or maintainer or manager):
                raise not_found()
            if target not in TRANSITIONS[order.status]:
                raise error(
                    409,
                    "order_state_conflict",
                    "Order state does not allow this transition",
                    current_state=order.status,
                    allowed_states=sorted(TRANSITIONS[order.status]),
                )
            if order.version != data["version"]:
                raise version_conflict(order.version)
            if target == "blocked" and not data.get("blocked_reason"):
                raise error(
                    422,
                    "validation_failed",
                    "blocked_reason is required",
                    fields=[{"field": "blocked_reason", "reason": "required"}],
                )
            old = order.status
            order.status, order.version = target, order.version + 1
            now = datetime.now(UTC)
            if target == "completed":
                order.completed_at = now
            if target == "cancelled":
                order.cancelled_at = now
            message = (
                data.get("note")
                or data.get("blocked_reason")
                or f"Order changed to {target}"
            )
            self._append(
                order,
                actor,
                target,
                message=message,
                from_status=old,
                to_status=target,
                details={"blocked_reason": data.get("blocked_reason")}
                if target == "blocked"
                else {},
            )
            event_type = (
                "maintenance.order_completed.v1"
                if target == "completed"
                else "maintenance.order_changed.v1"
            )
            payload = {
                "order_id": str(order.public_id),
                "property_id": str(order.property_id),
                "from_status": old,
                "to_status": target,
                "version": order.version,
                "occurred_at": now.isoformat(),
            }
            if target == "completed":
                payload["completed_at"] = now.isoformat()
            self._outbox(event_type, order, correlation_id, payload)
            self.db.flush()
            projection = "tenant" if actor.account_type == "customer" else "staff"
            body = order_view(order, self._events(order), projection)
            self._idempotency_finish(
                actor, "order_transition", key, digest, body, 200, order.public_id
            )
            return body

        return self._transaction(command)

    def comment(self, actor: Principal, order_id: UUID, data: dict, key: UUID) -> dict:
        def command():
            digest, replay = self._idempotency_start(
                actor, "order_comment", key, {"order_id": order_id, **data}
            )
            if replay is not None:
                return replay
            order = self._order(order_id, lock=True)
            if not self._visible(actor, order):
                raise not_found()
            if (
                actor.account_type == "staff"
                and actor.staff_id == order.assigned_staff_id
                and not actor.has("work_order:evidence_write")
                and not actor.is_admin
            ):
                raise not_found()
            if order.status in {"completed", "cancelled"}:
                raise error(
                    409,
                    "order_state_conflict",
                    "Terminal order cannot be commented on",
                    current_state=order.status,
                    allowed_states=sorted(OPEN_STATES),
                )
            if actor.account_type == "customer" and data["visibility"] != "public":
                raise forbidden()
            existing = self.db.scalar(
                sa.select(MaintenanceEvent).where(
                    MaintenanceEvent.order_id == order.id,
                    MaintenanceEvent.client_message_id == data["client_message_id"],
                )
            )
            if existing:
                if (
                    existing.actor_subject_id != actor.subject_id
                    or existing.message != data["content"]
                    or existing.visibility != data["visibility"]
                ):
                    raise error(
                        409,
                        "idempotency_conflict",
                        "Client message ID was used with another comment",
                        operation="order_comment",
                    )
                body = event_view(existing, tenant=actor.account_type == "customer")
            else:
                event = self._append(
                    order,
                    actor,
                    "commented",
                    visibility=data["visibility"],
                    message=data["content"],
                    client_message_id=data["client_message_id"],
                )
                self.db.flush()
                body = event_view(event, tenant=actor.account_type == "customer")
            self._idempotency_finish(
                actor, "order_comment", key, digest, body, 201, order.public_id
            )
            return body

        return self._transaction(command)

    def events(
        self, actor: Principal, order_id: UUID, projection: str, after: int, limit: int
    ) -> dict:
        order = self._order(order_id)
        if not self._visible(actor, order):
            raise not_found()
        tenant = actor.account_type == "customer" or projection == "tenant"
        query = sa.select(MaintenanceEvent).where(
            MaintenanceEvent.order_id == order.id, MaintenanceEvent.sequence_no > after
        )
        if tenant:
            query = query.where(MaintenanceEvent.visibility == "public")
        rows = list(
            self.db.scalars(query.order_by(MaintenanceEvent.sequence_no).limit(limit))
        )
        return {
            "items": [event_view(row, tenant=tenant) for row in rows],
            "next_cursor": None,
        }

    def order_access(self, actor: Principal, data: dict) -> dict:
        order = self._order(data["order_id"])
        if (
            data["subject_id"] != actor.subject_id
            or data["action"] != "report:read_work_context"
            or actor.account_type != "staff"
            or actor.role != "maintainer"
            or actor.staff_id is None
            or not actor.has("work_order:read_assigned")
            or not actor.has("report:read_work_context")
            or order.assigned_staff_id != actor.staff_id
        ):
            raise not_found()
        return {
            "allowed": True,
            "subject_id": str(actor.subject_id),
            "order_id": str(order.public_id),
            "property_id": str(order.property_id),
            "action": data["action"],
            "report_id": str(data["report_id"]),
        }

    def _deletion_blockers(self, subject_id: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                sa.select(MaintenanceOrder.public_id)
                .where(
                    MaintenanceOrder.reported_by_subject_id == subject_id,
                    MaintenanceOrder.status.in_(OPEN_STATES),
                )
                .order_by(MaintenanceOrder.public_id)
            )
        )

    def deletion_check(self, subject_id: UUID) -> dict:
        rows = self._deletion_blockers(subject_id)
        if rows:
            raise error(
                409,
                "open_maintenance_orders_block_deletion",
                "Open maintenance orders block deletion",
                blocker_count=len(rows),
                order_ids=[str(value) for value in rows],
            )
        return {"allowed": True, "blocker_count": 0, "order_ids": []}

    def deletion_status(self, subject_id: UUID) -> dict:
        rows = list(
            self.db.scalars(
                sa.select(MaintenanceOrder.public_id).where(
                    MaintenanceOrder.reported_by_subject_id == subject_id,
                    MaintenanceOrder.status.in_(OPEN_STATES),
                )
            )
        )
        return {
            "allowed": not rows,
            "blocker_count": len(rows),
            "order_ids": [str(value) for value in rows],
        }

    def process_deletion(self, request_id: UUID, subject_id: UUID) -> dict:
        def command():
            existing = self.db.get(SubjectDeletionRecord, request_id)
            if existing:
                if existing.subject_id != subject_id:
                    raise error(
                        409,
                        "idempotency_conflict",
                        "Deletion request has another subject",
                        operation="subject_deletion",
                    )
                return existing.result
            blockers = self.deletion_status(subject_id)
            if not blockers["allowed"]:
                raise error(
                    409,
                    "open_maintenance_orders_block_deletion",
                    "Open maintenance orders block deletion",
                    blocker_count=blockers["blocker_count"],
                    order_ids=blockers["order_ids"],
                )
            order_ids = list(
                self.db.scalars(
                    sa.select(MaintenanceOrder.id)
                    .where(MaintenanceOrder.reported_by_subject_id == subject_id)
                    .with_for_update()
                )
            )
            if order_ids:
                self.db.execute(
                    sa.delete(MaintenanceEvent).where(
                        MaintenanceEvent.order_id.in_(order_ids)
                    )
                )
                self.db.execute(
                    sa.delete(MaintenanceOrder).where(
                        MaintenanceOrder.id.in_(order_ids)
                    )
                )
            result = {
                "request_id": str(request_id),
                "status": "completed",
                "deleted_order_count": len(order_ids),
            }
            self.db.add(
                SubjectDeletionRecord(
                    request_id=request_id,
                    subject_id=subject_id,
                    status="completed",
                    result=result,
                )
            )
            return result

        result = self._transaction(command)
        self.dependencies.acknowledge_deletion(
            request_id,
            "completed",
            {"deleted_order_count": result["deleted_order_count"]},
        )
        return result
