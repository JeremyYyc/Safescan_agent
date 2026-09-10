import os
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.domain.principal import Principal
from app.models.tables import (Application, Building, CustomerLeaseSlot, IdempotencyRecord, Lease,
                               LeaseDocument, LeaseTenant, OutboxEvent, Party, Property, ProspectCase)
from app.services.leasing_service import LeasingService


DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL is required")


class FakeIdentity:
    def require_lease_eligible_customer(self, subject_id):
        return {"subject_id": str(subject_id), "account_type": "customer", "status": "active",
                "customer_status": "prospect"}


@pytest.fixture()
def factory():
    engine = create_engine(DB_URL, pool_size=8)
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE property_leasing.buildings CASCADE"))
        connection.execute(sa.text("TRUNCATE property_leasing.idempotency_records CASCADE"))
        connection.execute(sa.text("TRUNCATE property_leasing.customer_event_versions CASCADE"))
        connection.execute(sa.text("TRUNCATE property_leasing.outbox_events CASCADE"))
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def add_property(db: Session, suffix: str) -> Property:
    building = Building(reference=f"B-{suffix}", name=f"Building {suffix}", address="Sydney",
                        timezone="Australia/Sydney", status="active", attributes={})
    db.add(building)
    db.flush()
    prop = Property(building_id=building.id, reference=f"P-{suffix}", address="Sydney",
                    bedrooms=2, bathrooms=Decimal("1.0"), weekly_rent=Decimal("650.00"),
                    currency="AUD", status="under_offer", listing_visibility="public", attributes={})
    db.add(prop)
    db.flush()
    return prop


def add_application(db: Session, prop: Property, party: Party, staff_id, state: str,
                    suffix: str) -> tuple[ProspectCase, Application]:
    case = ProspectCase(prospect_party_id=party.id, property_id=prop.id,
                        assigned_consultant_staff_id=staff_id, stage="application", status="open",
                        opened_at=datetime.now(UTC), version=1)
    db.add(case)
    db.flush()
    application = Application(prospect_case_id=case.id, property_id=prop.id, applicant_id=party.id,
                              reference=f"APP-{suffix}", status=state,
                              desired_start_on=date.today() + timedelta(days=30), term_months=12,
                              occupants=1, note=None, version=1)
    db.add(application)
    db.flush()
    return case, application


def add_lease(db: Session, application: Application, prop: Property, party: Party, state: str,
              suffix: str) -> Lease:
    lease = Lease(application_id=application.id, property_id=prop.id, reference=f"L-{suffix}",
                  starts_on=date.today() + timedelta(days=30),
                  ends_on=date.today() + timedelta(days=395), weekly_rent=Decimal("650.00"),
                  currency="AUD", status=state,
                  offer_expires_at=datetime.now(UTC) + timedelta(days=7), version=1)
    db.add(lease)
    db.flush()
    db.add_all([
        LeaseTenant(lease_id=lease.id, party_id=party.id,
                    signing_status="signed" if state == "pending_signature" else "pending",
                    signed_at=datetime.now(UTC) if state == "pending_signature" else None, version=1),
        LeaseDocument(public_id=uuid4(), lease_id=lease.id, version=1, terms_payload={"v": 1},
                      terms_digest=LeasingService._terms_digest({"v": 1}), status="issued",
                      created_by_subject_id=uuid4()),
    ])
    if state == "pending_signature":
        lease.tenant_signed_at = datetime.now(UTC)
        lease.company_signed_at = datetime.now(UTC)
    db.flush()
    return lease


def test_execute_closes_related_aggregates_and_outbox_atomically(factory) -> None:
    staff_id, staff_subject, customer_subject = uuid4(), uuid4(), uuid4()
    with factory() as db:
        prop = add_property(db, uuid4().hex[:6])
        party = Party(party_type="person", subject_id=customer_subject, name="Applicant",
                      contact={}, status="active")
        db.add(party)
        db.flush()
        winner_case, winner_app = add_application(db, prop, party, staff_id, "approved", "WIN")
        winner = add_lease(db, winner_app, prop, party, "pending_signature", "WIN")
        db.add(CustomerLeaseSlot(customer_subject_id=customer_subject, lease_id=winner.id,
                                 status="pending_signature", reserved_at=datetime.now(UTC), version=1))
        losers = []
        for index, state in enumerate(("draft", "submitted", "reviewing", "approved")):
            case, application = add_application(db, prop, party, staff_id, state, f"LOSE-{index}")
            losers.append((case, application))
            if state == "approved":
                add_lease(db, application, prop, party, "draft", "LOSE")
        db.commit()
        winning_public_id, winning_version = winner.public_id, winner.version

    settings = Settings(database_url=DB_URL, jwt_secret="test-secret-that-is-at-least-24-characters")
    actor = Principal(subject_id=staff_subject, account_type="staff",
                      scopes=frozenset({"lease:execute"}), claims={}, staff_id=staff_id,
                      role="leasing_consultant")
    execute_key = uuid4()
    with factory() as db:
        service = LeasingService(db, FakeIdentity(), settings)
        result = service.execute_lease(actor, winning_public_id, {"version": winning_version},
                                       execute_key, uuid4())
        assert result["status"] == "executed"

    with factory() as db:
        replay = LeasingService(db, FakeIdentity(), settings).execute_lease(
            actor, winning_public_id, {"version": winning_version}, execute_key, uuid4())
        assert replay["id"] == result["id"]
        assert replay["status"] == result["status"]
        saved_winner = db.scalar(sa.select(Lease).where(Lease.public_id == winning_public_id))
        saved_apps = list(db.scalars(sa.select(Application).where(Application.id != saved_winner.application_id)
                                     .order_by(Application.id)))
        assert [row.status for row in saved_apps] == ["ineligible", "ineligible", "ineligible", "expired"]
        assert all(row.closed_reason == "another_lease_executed" for row in saved_apps)
        assert all(row.winning_lease_id == saved_winner.id for row in saved_apps)
        draft = db.scalar(sa.select(Lease).where(Lease.reference == "L-LOSE"))
        assert draft.status == "cancelled"
        assert all(row.status == "closed" and row.stage == "lost" for row in db.scalars(
            sa.select(ProspectCase).where(ProspectCase.id != winner_case.id)))
        events = list(db.scalars(sa.select(OutboxEvent)))
        assert len([event for event in events if event.event_type == "application.invalidated.v1"]) == 4
        assert {"lease.executed.v1", "customer.tenancy_status_changed.v1"}.issubset(
            {event.event_type for event in events}
        )


def test_customer_slot_allows_only_one_concurrent_reservation(factory) -> None:
    customer_subject = uuid4()
    with factory() as db:
        party = Party(party_type="person", subject_id=customer_subject, name="Applicant",
                      contact={}, status="active")
        db.add(party)
        db.flush()
        lease_ids = []
        for index in range(2):
            prop = add_property(db, f"SLOT-{index}-{uuid4().hex[:4]}")
            _, application = add_application(db, prop, party, uuid4(), "approved", f"SLOT-{index}")
            lease_ids.append(add_lease(db, application, prop, party, "draft", f"SLOT-{index}").id)
        db.commit()

    barrier = threading.Barrier(2)
    results = []

    def reserve(lease_id):
        with factory() as db:
            barrier.wait()
            db.add(CustomerLeaseSlot(customer_subject_id=customer_subject, lease_id=lease_id,
                                     status="pending_signature", reserved_at=datetime.now(UTC), version=1))
            try:
                db.commit()
                results.append("ok")
            except IntegrityError:
                db.rollback()
                results.append("conflict")

    threads = [threading.Thread(target=reserve, args=(lease_id,)) for lease_id in lease_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == ["conflict", "ok"]


def test_property_date_exclusion_allows_only_one_overlapping_lease(factory) -> None:
    with factory() as db:
        prop = add_property(db, f"DATE-{uuid4().hex[:4]}")
        lease_ids = []
        for index in range(2):
            party = Party(party_type="person", subject_id=uuid4(), name=f"Applicant {index}",
                          contact={}, status="active")
            db.add(party)
            db.flush()
            _, application = add_application(db, prop, party, uuid4(), "approved", f"DATE-{index}")
            lease_ids.append(add_lease(db, application, prop, party, "draft", f"DATE-{index}").id)
        db.commit()

    barrier = threading.Barrier(2)
    results = []

    def make_pending(lease_id):
        with factory() as db:
            lease = db.get(Lease, lease_id)
            barrier.wait()
            lease.status = "pending_signature"
            try:
                db.commit()
                results.append("ok")
            except IntegrityError:
                db.rollback()
                results.append("conflict")

    threads = [threading.Thread(target=make_pending, args=(lease_id,)) for lease_id in lease_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == ["conflict", "ok"]
