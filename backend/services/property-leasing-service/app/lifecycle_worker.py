import os
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

import sqlalchemy as sa

from app.core.database import get_session_factory
from app.models.tables import (Application, Building, CustomerEventVersion, CustomerLeaseSlot,
                               Lease, LeaseTenant, OutboxEvent, Party, Property, ProspectCase)


NAMESPACE = UUID("5d96d50c-ec79-4fd5-a3f1-38b98790a2ab")


def _event(db, event_type: str, aggregate_type: str, aggregate_id: UUID, version: int,
           correlation_id: UUID, payload: dict) -> None:
    db.add(OutboxEvent(event_id=uuid5(NAMESPACE, f"{event_type}:{aggregate_id}:{version}"),
                       event_type=event_type, schema_version=1, aggregate_type=aggregate_type,
                       aggregate_id=aggregate_id, aggregate_version=version,
                       correlation_id=correlation_id, payload=payload, status="pending", attempts=0,
                       available_at=datetime.now(UTC)))


def tick(as_of: datetime | None = None, batch_size: int = 100) -> int:
    """Claim due leases with SKIP LOCKED and apply time-driven transitions atomically."""
    as_of = as_of or datetime.now(UTC)
    db = get_session_factory()()
    changed = 0
    try:
        due = list(db.scalars(sa.select(Lease).join(Property, Property.id == Lease.property_id)
                              .outerjoin(Building, Building.id == Property.building_id).where(sa.or_(
            sa.and_(Lease.status == "pending_signature", Lease.offer_expires_at <= as_of),
            sa.and_(Lease.status == "executed",
                    Lease.starts_on <= sa.cast(sa.func.timezone(sa.func.coalesce(Building.timezone, "UTC"),
                                                               as_of), sa.Date)),
            sa.and_(Lease.status == "active",
                    Lease.ends_on < sa.cast(sa.func.timezone(sa.func.coalesce(Building.timezone, "UTC"),
                                                            as_of), sa.Date)),
        )).order_by(Lease.status, Lease.id).with_for_update(of=Lease, skip_locked=True)
                   .limit(batch_size)))
        for lease in due:
            correlation_id = uuid4()
            tenant = db.scalar(sa.select(LeaseTenant).where(LeaseTenant.lease_id == lease.id))
            party = db.get(Party, tenant.party_id)
            slot = db.scalar(sa.select(CustomerLeaseSlot).where(
                CustomerLeaseSlot.customer_subject_id == party.subject_id).with_for_update())
            prop = db.scalar(sa.select(Property).where(Property.id == lease.property_id).with_for_update())
            if lease.status == "pending_signature":
                lease.status = "expired"
                if slot and slot.lease_id == lease.id:
                    db.delete(slot)
                application = db.scalar(sa.select(Application).where(
                    Application.id == lease.application_id).with_for_update())
                application.status = "expired"
                application.closed_reason = "offer_expired"
                application.closed_at = as_of
                application.version += 1
                case = db.scalar(sa.select(ProspectCase).where(
                    ProspectCase.id == application.prospect_case_id).with_for_update())
                case.stage, case.status, case.closed_at = "lost", "closed", as_of
                case.version += 1
                prop.status = "marketing"
                event_type = "lease.expired.v1"
            elif lease.status == "executed":
                lease.status = "active"
                if not slot or slot.lease_id != lease.id:
                    raise RuntimeError("lease slot mismatch during activation")
                slot.status = "active"
                slot.version += 1
                event_type = "lease.activated.v1"
            else:
                lease.status = "ended"
                lease.ended_at = as_of
                if slot and slot.lease_id == lease.id:
                    db.delete(slot)
                prop.status = "marketing"
                event_type = "lease.ended.v1"
            lease.version += 1
            _event(db, event_type, "lease", lease.public_id, lease.version, correlation_id,
                   {"lease_id": str(lease.public_id), "property_id": str(prop.public_id),
                    "customer_subject_id": str(party.subject_id), "occurred_at": as_of.isoformat()})
            if event_type == "lease.ended.v1":
                version = db.scalar(sa.select(CustomerEventVersion).where(
                    CustomerEventVersion.customer_subject_id == party.subject_id).with_for_update())
                if version is None:
                    version = CustomerEventVersion(customer_subject_id=party.subject_id, aggregate_version=1)
                    db.add(version)
                else:
                    version.aggregate_version += 1
                db.flush()
                _event(db, "customer.tenancy_status_changed.v1", "customer", party.subject_id,
                       version.aggregate_version, correlation_id,
                       {"customer_subject_id": str(party.subject_id),
                        "lease_id": str(lease.public_id), "to_status": "former_tenant",
                        "aggregate_version": version.aggregate_version,
                        "occurred_at": as_of.isoformat()})
            changed += 1
        db.commit()
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    interval = float(os.getenv("LEASE_LIFECYCLE_POLL_SECONDS", "5"))
    while True:
        tick()
        time.sleep(interval)


if __name__ == "__main__":
    main()
