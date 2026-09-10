from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.tables import (
    auth_events,
    customer_profiles,
    customer_status_events,
    outbox_events,
    subject_deletion_acknowledgements,
    subject_deletion_requests,
    subject_deletion_tombstones,
    users,
)


class DeletionMapper:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: int, *, for_update: bool = False):
        statement = sa.select(subject_deletion_requests).where(
            subject_deletion_requests.c.user_id == user_id,
            subject_deletion_requests.c.status != "completed",
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def get(self, public_id: UUID | str, *, for_update: bool = False):
        statement = sa.select(subject_deletion_requests).where(
            subject_deletion_requests.c.public_id == public_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def create(self, *, user_id: int, subject_id: UUID, reason: str | None,
               idempotency_key: str, required_services: list[str]) -> dict:
        now = datetime.now().astimezone()
        return dict(self.session.execute(subject_deletion_requests.insert().values(
            public_id=uuid4(), user_id=user_id, subject_id=subject_id, status="checking",
            reason=reason, idempotency_key=idempotency_key, blocker_summary={},
            required_services=required_services, created_at=now, updated_at=now,
        ).returning(subject_deletion_requests)).mappings().one())

    def set_status(self, request_id: int, status: str, *, blockers: dict | None = None) -> dict:
        values = {"status": status, "updated_at": datetime.now().astimezone()}
        if blockers is not None:
            values["blocker_summary"] = blockers
        return dict(self.session.execute(subject_deletion_requests.update().where(
            subject_deletion_requests.c.id == request_id
        ).values(**values).returning(subject_deletion_requests)).mappings().one())

    def publish_requested(self, request: dict, correlation_id: UUID) -> None:
        now = datetime.now().astimezone()
        self.session.execute(outbox_events.insert().values(
            event_id=uuid4(), event_type="identity.subject_deletion_requested.v1", schema_version=1,
            aggregate_type="subject_deletion", aggregate_id=request["public_id"], aggregate_version=1,
            correlation_id=correlation_id,
            payload={"request_id": str(request["public_id"]),
                     "subject_id": str(request["subject_id"]),
                     "requested_at": request["created_at"].isoformat()},
            status="pending", attempts=0, available_at=now, created_at=now, updated_at=now,
        ))

    def acknowledgements(self, request_id: int) -> list[dict]:
        return list(self.session.execute(sa.select(subject_deletion_acknowledgements).where(
            subject_deletion_acknowledgements.c.request_id == request_id
        ).order_by(subject_deletion_acknowledgements.c.service)).mappings())

    def acknowledge(self, *, request_id: int, service: str, status: str, details: dict) -> tuple[dict, bool]:
        now = datetime.now().astimezone()
        existing = self.session.execute(sa.select(subject_deletion_acknowledgements).where(
            subject_deletion_acknowledgements.c.request_id == request_id,
            subject_deletion_acknowledgements.c.service == service,
        ).with_for_update()).mappings().first()
        if existing and existing["status"] == status and existing["details_redacted"] == details:
            return dict(existing), True
        if existing:
            row = self.session.execute(subject_deletion_acknowledgements.update().where(
                subject_deletion_acknowledgements.c.id == existing["id"]
            ).values(status=status, details_redacted=details,
                     attempt=subject_deletion_acknowledgements.c.attempt + 1,
                     received_at=now, updated_at=now)
                .returning(subject_deletion_acknowledgements)).mappings().one()
            return dict(row), False
        row = self.session.execute(subject_deletion_acknowledgements.insert().values(
            request_id=request_id, service=service, status=status, details_redacted=details,
            attempt=1, received_at=now, created_at=now, updated_at=now,
        ).returning(subject_deletion_acknowledgements)).mappings().one()
        return dict(row), False

    def finalize(self, request: dict, *, fingerprint: bytes, fingerprint_version: int) -> None:
        now = datetime.now().astimezone()
        user_id = request["user_id"]
        profile_id = self.session.scalar(sa.select(customer_profiles.c.id).where(
            customer_profiles.c.user_id == user_id
        ))
        if profile_id is not None:
            self.session.execute(customer_status_events.delete().where(
                customer_status_events.c.customer_id == profile_id
            ))
            self.session.execute(customer_profiles.delete().where(customer_profiles.c.id == profile_id))
        self.session.execute(auth_events.update().where(auth_events.c.user_id == user_id).values(
            details_redacted={}
        ))
        self.session.execute(pg_insert(subject_deletion_tombstones).values(
            deletion_request_id=request["public_id"], subject_fingerprint=fingerprint,
            fingerprint_version=fingerprint_version, status="completed", completed_at=now,
        ).on_conflict_do_nothing(index_elements=[subject_deletion_tombstones.c.deletion_request_id]))
        self.session.execute(subject_deletion_requests.update().where(
            subject_deletion_requests.c.id == request["id"]
        ).values(user_id=None, subject_id=None, reason=None, idempotency_key="erased",
                 blocker_summary={}, status="completed", updated_at=now))
        self.session.execute(outbox_events.update().where(
            outbox_events.c.aggregate_type == "subject_deletion",
            outbox_events.c.aggregate_id == request["public_id"],
        ).values(payload={"request_id": str(request["public_id"]), "subject_erased": True},
                 updated_at=now))
        self.session.execute(users.delete().where(users.c.id == user_id))

    def tombstone_exists(self, fingerprints: list[bytes]):
        if not fingerprints:
            return None
        return self.session.execute(sa.select(subject_deletion_tombstones).where(
            subject_deletion_tombstones.c.subject_fingerprint.in_(fingerprints)
        )).mappings().first()
