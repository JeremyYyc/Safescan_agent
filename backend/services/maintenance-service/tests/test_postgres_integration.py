import os
import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from app.core.config import Settings
from app.domain.principal import Principal
from app.models.tables import MaintenanceEvent, MaintenanceOrder, OutboxEvent
from app.services.maintenance import MaintenanceService
from safescan_common.http.errors import ApiError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL is required"),
]


class FakeDependencies:
    def __init__(
        self,
        *,
        lease_allowed=True,
        lease_status="active",
        property_allowed=True,
        relationship_changes=False,
    ):
        self.lease_allowed = lease_allowed
        self.lease_status = lease_status
        self.property_allowed = property_allowed
        self.relationship_changes = relationship_changes
        self.lease_calls = 0
        self.acks = 0

    def lease_access(self, actor, lease_id, property_id):
        self.lease_calls += 1
        return {
            "allowed": self.lease_allowed,
            "lease_id": str(lease_id),
            "property_id": str(property_id),
            "status": self.lease_status,
            "lease_version": 3
            + int(self.relationship_changes and self.lease_calls > 1),
            "relationship_version": 2,
        }

    def property_access(self, actor, property_id, action):
        return self.property_allowed

    def require_active_maintainer(self, staff_id):
        return {"id": str(staff_id), "status": "active", "role": "maintainer"}

    def acknowledge_deletion(self, request_id, status, details):
        self.acks += 1
        return {"accepted": True}


def truncate_maintenance(engine):
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE maintenance.maintenance_orders CASCADE"))
        connection.execute(sa.text("TRUNCATE maintenance.idempotency_records CASCADE"))
        connection.execute(
            sa.text("TRUNCATE maintenance.subject_deletion_records CASCADE")
        )
        connection.execute(sa.text("TRUNCATE maintenance.outbox_events CASCADE"))


@pytest.fixture()
def factory():
    engine = create_engine(DB_URL, pool_size=8)
    truncate_maintenance(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            truncate_maintenance(engine)
        finally:
            engine.dispose()


def settings():
    return Settings(
        database_url=DB_URL, jwt_secret="test-secret-that-is-at-least-24-characters"
    )


def tenant(subject=None):
    return Principal(
        subject_id=subject or uuid4(),
        account_type="customer",
        scopes=frozenset({"maintenance:self:create"}),
        claims={},
        customer_status="tenant",
    )


def manager(staff_id=None, admin=False):
    scopes = {"maintenance:assign_assigned", "maintenance:update_assigned"}
    if admin:
        scopes.add("maintenance:manage_all")
    return Principal(
        subject_id=uuid4(),
        account_type="staff",
        scopes=frozenset(scopes),
        claims={},
        staff_id=staff_id or uuid4(),
        role="manager_admin" if admin else "property_manager",
    )


def maintainer(staff_id):
    return Principal(
        subject_id=uuid4(),
        account_type="staff",
        scopes=frozenset(
            {
                "work_order:read_assigned",
                "work_order:update_assigned",
                "work_order:evidence_write",
                "property:read_work_context",
                "report:read_work_context",
            }
        ),
        claims={},
        staff_id=staff_id,
        role="maintainer",
    )


def create_order(factory, actor=None, deps=None):
    actor, deps = actor or tenant(), deps or FakeDependencies()
    property_id, lease_id, key = uuid4(), uuid4(), uuid4()
    with factory() as db:
        result = MaintenanceService(db, deps, settings()).create(
            actor,
            {
                "property_id": property_id,
                "lease_id": lease_id,
                "summary": "Leak",
                "description": "Under sink",
                "priority": "normal",
            },
            key,
            uuid4(),
        )
    return actor, deps, result, key


def test_tenant_active_lease_creation_is_atomic_and_idempotent(factory):
    actor, deps, result, key = create_order(factory)
    with factory() as db:
        replay = MaintenanceService(db, deps, settings()).create(
            actor,
            {
                "property_id": result["property"]["id"],
                "lease_id": result["lease_id"],
                "summary": "Leak",
                "description": "Under sink",
                "priority": "normal",
            },
            key,
            uuid4(),
        )
        assert replay["id"] == result["id"]
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceOrder)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceEvent)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(OutboxEvent)) == 1
    assert deps.lease_calls == 2


def test_wrong_or_inactive_lease_creates_nothing(factory):
    deps = FakeDependencies(lease_allowed=False)
    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).create(
            tenant(),
            {
                "property_id": uuid4(),
                "lease_id": uuid4(),
                "summary": "Leak",
                "description": None,
                "priority": "normal",
            },
            uuid4(),
            uuid4(),
        )
    assert caught.value.status_code == 404
    with factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceOrder)) == 0


@pytest.mark.parametrize(
    "lease_status", ["draft", "pending_signature", "executed", "ended", "terminated"]
)
def test_non_active_or_historical_lease_creates_nothing(factory, lease_status):
    deps = FakeDependencies(lease_status=lease_status)
    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).create(
            tenant(),
            {
                "property_id": uuid4(),
                "lease_id": uuid4(),
                "summary": "Leak",
                "description": None,
                "priority": "normal",
            },
            uuid4(),
            uuid4(),
        )
    assert (caught.value.status_code, caught.value.code) == (404, "resource_not_found")


def test_relationship_version_change_before_commit_creates_nothing(factory):
    deps = FakeDependencies(relationship_changes=True)
    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).create(
            tenant(),
            {
                "property_id": uuid4(),
                "lease_id": uuid4(),
                "summary": "Leak",
                "description": None,
                "priority": "normal",
            },
            uuid4(),
            uuid4(),
        )
    assert (caught.value.status_code, caught.value.code) == (404, "resource_not_found")
    with factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceOrder)) == 0


def test_tenant_visibility_and_idor_are_identical(factory):
    owner, deps, result, _ = create_order(factory)
    stranger = tenant()
    with factory() as db:
        service = MaintenanceService(db, deps, settings())
        assert service.get(owner, result["id"])["id"] == result["id"]
        errors = []
        for target in (UUID(result["id"]), uuid4()):
            try:
                service.get(stranger, target)
            except ApiError as exc:
                errors.append((exc.status_code, exc.code, exc.details))
        assert errors == [
            (404, "resource_not_found", {}),
            (404, "resource_not_found", {}),
        ]


def test_manager_scope_and_admin_global_visibility(factory):
    _, _, result, _ = create_order(factory)
    with factory() as db:
        with pytest.raises(ApiError):
            MaintenanceService(
                db, FakeDependencies(property_allowed=False), settings()
            ).get(manager(), result["id"])
        assert (
            MaintenanceService(
                db, FakeDependencies(property_allowed=False), settings()
            ).get(manager(admin=True), result["id"])["id"]
            == result["id"]
        )


def test_role_scoped_lists(factory):
    owner, deps, result, _ = create_order(factory)
    assignee = uuid4()
    with factory() as db:
        assigned = MaintenanceService(db, deps, settings()).assign(
            manager(),
            result["id"],
            {"assigned_staff_id": assignee, "version": 1, "note": None},
            uuid4(),
            uuid4(),
        )
    with factory() as db:
        service = MaintenanceService(db, deps, settings())
        assert [
            row["id"]
            for row in service.list(owner, None, None, None, None, None, 20)["items"]
        ] == [result["id"]]
        assert [
            row["id"]
            for row in service.list(
                maintainer(assignee), None, None, None, None, None, 20
            )["items"]
        ] == [result["id"]]
        assert (
            service.list(maintainer(uuid4()), None, None, None, None, None, 20)["items"]
            == []
        )
        assert [
            row["id"]
            for row in service.list(
                manager(admin=True), None, None, None, None, None, 20
            )["items"]
        ] == [result["id"]]
        assert assigned["assigned_staff"]["id"] == str(assignee)


def test_report_work_context_access_binds_subject_assignment_and_property(factory):
    _, deps, result, _ = create_order(factory)
    assignee = uuid4()
    with factory() as db:
        MaintenanceService(db, deps, settings()).assign(
            manager(),
            result["id"],
            {"assigned_staff_id": assignee, "version": 1, "note": None},
            uuid4(),
            uuid4(),
        )
    reader, report_id = maintainer(assignee), uuid4()
    payload = {
        "subject_id": reader.subject_id,
        "order_id": UUID(result["id"]),
        "action": "report:read_work_context",
        "report_id": report_id,
    }
    with factory() as db:
        access = MaintenanceService(db, deps, settings()).order_access(reader, payload)
    assert access == {
        "allowed": True,
        "subject_id": str(reader.subject_id),
        "order_id": result["id"],
        "property_id": result["property"]["id"],
        "action": "report:read_work_context",
        "report_id": str(report_id),
    }
    for bad_reader, bad_subject in (
        (maintainer(uuid4()), reader.subject_id),
        (reader, uuid4()),
    ):
        with factory() as db, pytest.raises(ApiError) as hidden:
            MaintenanceService(db, deps, settings()).order_access(
                bad_reader, {**payload, "subject_id": bad_subject}
            )
        assert (hidden.value.status_code, hidden.value.code, hidden.value.details) == (
            404,
            "resource_not_found",
            {},
        )


def test_assignment_maintainer_transitions_and_timeline(factory):
    _, deps, result, _ = create_order(factory)
    assignee, boss = uuid4(), manager()
    with factory() as db:
        assigned = MaintenanceService(db, deps, settings()).assign(
            boss,
            result["id"],
            {"assigned_staff_id": assignee, "version": 1, "note": "Please fix"},
            uuid4(),
            uuid4(),
        )
    worker = maintainer(assignee)
    version = assigned["version"]
    for target in ("in_progress", "blocked", "in_progress", "completed"):
        with factory() as db:
            payload = {
                "to_status": target,
                "version": version,
                "note": target,
                "blocked_reason": "parts" if target == "blocked" else None,
            }
            updated = MaintenanceService(db, deps, settings()).transition(
                worker, result["id"], payload, uuid4(), uuid4()
            )
            version = updated["version"]
    assert updated["completed_at"] is not None
    assert [event["sequence_no"] for event in updated["timeline"]] == list(range(1, 7))


def test_maintainer_cannot_process_another_assignment(factory):
    _, deps, result, _ = create_order(factory)
    with factory() as db:
        assigned = MaintenanceService(db, deps, settings()).assign(
            manager(),
            result["id"],
            {"assigned_staff_id": uuid4(), "version": 1, "note": None},
            uuid4(),
            uuid4(),
        )
    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).transition(
            maintainer(uuid4()),
            result["id"],
            {
                "to_status": "in_progress",
                "version": assigned["version"],
                "note": None,
                "blocked_reason": None,
            },
            uuid4(),
            uuid4(),
        )
    assert (caught.value.status_code, caught.value.code) == (404, "resource_not_found")


def test_old_version_and_illegal_transition_do_not_overwrite(factory):
    _, deps, result, _ = create_order(factory)
    with factory() as db:
        assigned = MaintenanceService(db, deps, settings()).assign(
            manager(),
            result["id"],
            {"assigned_staff_id": uuid4(), "version": 1, "note": None},
            uuid4(),
            uuid4(),
        )
    with factory() as db, pytest.raises(ApiError) as old:
        MaintenanceService(db, deps, settings()).assign(
            manager(),
            result["id"],
            {"assigned_staff_id": uuid4(), "version": 1, "note": None},
            uuid4(),
            uuid4(),
        )
    assert old.value.code == "version_conflict"
    with factory() as db, pytest.raises(ApiError) as illegal:
        MaintenanceService(db, deps, settings()).transition(
            manager(admin=True),
            result["id"],
            {
                "to_status": "completed",
                "version": assigned["version"],
                "note": None,
                "blocked_reason": None,
            },
            uuid4(),
            uuid4(),
        )
    assert illegal.value.code == "order_state_conflict"


@pytest.mark.concurrency
def test_concurrent_assignment_has_one_winner(factory):
    _, deps, result, _ = create_order(factory)
    barrier, outcomes = threading.Barrier(2), []

    def run():
        with factory() as db:
            barrier.wait()
            try:
                MaintenanceService(db, deps, settings()).assign(
                    manager(),
                    result["id"],
                    {"assigned_staff_id": uuid4(), "version": 1, "note": None},
                    uuid4(),
                    uuid4(),
                )
                outcomes.append("ok")
            except ApiError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=run) for _ in range(2)]
    [thread.start() for thread in threads]
    [thread.join(10) for thread in threads]
    assert sorted(outcomes) == ["ok", "version_conflict"]


@pytest.mark.concurrency
def test_concurrent_reporter_updates_have_one_winner(factory):
    owner, deps, result, _ = create_order(factory)
    barrier, outcomes = threading.Barrier(2), []

    def run(summary):
        with factory() as db:
            barrier.wait()
            try:
                MaintenanceService(db, deps, settings()).update(
                    owner,
                    result["id"],
                    {
                        "summary": summary,
                        "description": None,
                        "priority": None,
                        "version": 1,
                    },
                    uuid4(),
                    uuid4(),
                )
                outcomes.append("ok")
            except ApiError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=run, args=(value,)) for value in ("A", "B")]
    [thread.start() for thread in threads]
    [thread.join(10) for thread in threads]
    assert sorted(outcomes) == ["ok", "version_conflict"]


@pytest.mark.concurrency
def test_concurrent_same_idempotency_key_creates_one_order(factory):
    owner, deps, key, property_id, lease_id = (
        tenant(),
        FakeDependencies(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    barrier, ids = threading.Barrier(2), []

    def run():
        with factory() as db:
            barrier.wait()
            result = MaintenanceService(db, deps, settings()).create(
                owner,
                {
                    "property_id": property_id,
                    "lease_id": lease_id,
                    "summary": "Same",
                    "description": None,
                    "priority": "normal",
                },
                key,
                uuid4(),
            )
            ids.append(result["id"])

    threads = [threading.Thread(target=run) for _ in range(2)]
    [thread.start() for thread in threads]
    [thread.join(10) for thread in threads]
    assert len(set(ids)) == 1
    with factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceOrder)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(MaintenanceEvent)) == 1


def test_public_comment_is_stable_and_internal_is_hidden(factory):
    owner, deps, result, _ = create_order(factory)
    message_id, key = uuid4(), uuid4()
    with factory() as db:
        service = MaintenanceService(db, deps, settings())
        first = service.comment(
            owner,
            result["id"],
            {
                "content": "More water",
                "visibility": "public",
                "client_message_id": message_id,
            },
            key,
        )
    with factory() as db:
        replay = MaintenanceService(db, deps, settings()).comment(
            owner,
            result["id"],
            {
                "content": "More water",
                "visibility": "public",
                "client_message_id": message_id,
            },
            key,
        )
        assert replay == first

    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).comment(
            tenant(),
            result["id"],
            {"content": "Forged", "visibility": "public", "client_message_id": uuid4()},
            uuid4(),
        )
    assert (caught.value.status_code, caught.value.code) == (404, "resource_not_found")


def test_client_message_id_cannot_replay_another_actor_comment(factory):
    owner, deps, result, _ = create_order(factory)
    message_id = uuid4()
    with factory() as db:
        MaintenanceService(db, deps, settings()).comment(
            owner,
            result["id"],
            {
                "content": "Original",
                "visibility": "public",
                "client_message_id": message_id,
            },
            uuid4(),
        )
    with factory() as db, pytest.raises(ApiError) as caught:
        MaintenanceService(db, deps, settings()).comment(
            manager(admin=True),
            result["id"],
            {
                "content": "Internal",
                "visibility": "internal",
                "client_message_id": message_id,
            },
            uuid4(),
        )
    assert caught.value.code == "idempotency_conflict"


def test_postgres_assignment_and_event_constraints(factory):
    with factory() as db:
        db.add(
            MaintenanceOrder(
                public_id=uuid4(),
                property_id=uuid4(),
                lease_id=uuid4(),
                reference=f"WO-{uuid4().hex}",
                summary="bad",
                priority="normal",
                status="assigned",
                version=1,
                next_event_sequence=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_deletion_blocker_then_idempotent_completion(factory):
    owner, deps, result, _ = create_order(factory)
    with factory() as db:
        service = MaintenanceService(db, deps, settings())
        with pytest.raises(ApiError) as eligibility:
            service.deletion_check(owner.subject_id)
        assert eligibility.value.code == "open_maintenance_orders_block_deletion"
        assert eligibility.value.details["blocker_count"] == 1
        with pytest.raises(ApiError) as caught:
            service.process_deletion(uuid4(), owner.subject_id)
        assert caught.value.code == "open_maintenance_orders_block_deletion"
    with factory() as db:
        order = db.scalar(
            sa.select(MaintenanceOrder).where(
                MaintenanceOrder.public_id == result["id"]
            )
        )
        order.status, order.cancelled_at = "cancelled", datetime.now(UTC)
        db.commit()
    request_id = uuid4()
    with factory() as db:
        completed = MaintenanceService(db, deps, settings()).process_deletion(
            request_id, owner.subject_id
        )
    with factory() as db:
        replay = MaintenanceService(db, deps, settings()).process_deletion(
            request_id, owner.subject_id
        )
    assert completed == replay
    assert deps.acks == 2
