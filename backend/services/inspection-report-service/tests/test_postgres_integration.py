import os
import re
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from inspection_report_service.repository import ReportRepository


DB_URL = os.getenv("REPORT_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="REPORT_TEST_DATABASE_URL is required")


@pytest.fixture(scope="session")
def factory():
    url = make_url(DB_URL)
    if url.get_backend_name() != "postgresql" or not url.database or not re.search(
        r"(^|[_-])(ci|test)([_-]|$)", url.database.lower()
    ):
        pytest.fail("Report integration tests require a disposable PostgreSQL test/ci database")
    engine = sa.create_engine(DB_URL, pool_size=8, max_overflow=8, pool_pre_ping=True)
    required = {"report_idempotency_records", "report_audit_events", "report_jobs"}
    missing = required.difference(sa.inspect(engine).get_table_names(schema="inspection_report"))
    if missing:
        pytest.fail(f"Report migration 20260913_0009 is required; missing {sorted(missing)}")
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean(factory):
    with factory() as db, db.begin():
        db.execute(sa.text(
            "TRUNCATE inspection_report.report_idempotency_records,"
            "inspection_report.report_audit_events,inspection_report.report_job_events,"
            "inspection_report.report_job_steps,inspection_report.report_assets,"
            "inspection_report.report_analysis,inspection_report.report_pdf,"
            "inspection_report.report_jobs,inspection_report.files,inspection_report.reports CASCADE"
        ))


def create_report(factory, *, account="staff", lease_id=None, actor=None, key=None):
    actor, property_id = actor or uuid4(), uuid4()
    with factory() as db:
        value = ReportRepository(db).create_report(
            actor, account, property_id, lease_id, "Integration report", key or uuid4(),
            uuid4(), "deterministic-test-adapter",
        )
    return value, actor, property_id


def add_file(factory, report, actor):
    with factory() as db:
        return ReportRepository(db).save_uploaded_file(
            report_internal_id=report["id"], actor=actor, public_id=uuid4(),
            bucket="private-test", object_key=f"input/{uuid4().hex}", original_name="test.mp4",
            mime_type="video/mp4", size=4, sha256="a" * 64, key=uuid4(), request_digest="upload",
        )


def add_job(factory, report, actor, file_row, key=None):
    with factory() as db:
        return ReportRepository(db).create_job(
            report=report, actor=actor, file_id=file_row["public_id"], attributes={},
            key=key or uuid4(), pipeline_version="deterministic-test-adapter", max_attempts=3,
        )


def test_formal_report_constraints_require_property_and_customer_lease(factory) -> None:
    base = {
        "public": uuid4(), "actor": uuid4(), "title": "invalid",
        "pipeline": "deterministic-test-adapter",
    }
    with factory() as db:
        with pytest.raises(IntegrityError):
            with db.begin():
                db.execute(sa.text(
                    "INSERT INTO inspection_report.reports "
                    "(public_id,created_by_subject_id,created_by_account_type,is_formal,report_kind,source,title,status,schema_version,pipeline_version) "
                    "VALUES (:public,:actor,'staff',true,'analysis','video_analysis',:title,'draft',1,:pipeline)"
                ), base)
        db.rollback()
        with pytest.raises(IntegrityError):
            with db.begin():
                db.execute(sa.text(
                    "INSERT INTO inspection_report.reports "
                    "(public_id,property_id,created_by_subject_id,created_by_account_type,is_formal,report_kind,source,title,status,schema_version,pipeline_version) "
                    "VALUES (:public,:property,:actor,'customer',true,'analysis','video_analysis',:title,'draft',1,:pipeline)"
                ), {**base, "public": uuid4(), "property": uuid4()})


def test_tenant_binding_and_idempotency_survive_new_sessions(factory) -> None:
    lease_id, key, actor = uuid4(), uuid4(), uuid4()
    first, _, property_id = create_report(factory, account="customer", lease_id=lease_id,
                                           actor=actor, key=key)
    with factory() as db:
        replay = ReportRepository(db).create_report(
            actor, "customer", property_id, lease_id, "Integration report", key,
            uuid4(), "deterministic-test-adapter",
        )
    assert replay["public_id"] == first["public_id"]
    assert replay["property_id"] == property_id
    assert replay["source_lease_id"] == lease_id


def test_same_idempotency_key_creates_one_job_and_report(factory) -> None:
    report, actor, _ = create_report(factory)
    file_row = add_file(factory, report, actor)
    key = uuid4()
    first = add_job(factory, report, actor, file_row, key)
    with factory() as db:
        replay = ReportRepository(db).create_job(
            report=report, actor=actor, file_id=file_row["public_id"], attributes={}, key=key,
            pipeline_version="deterministic-test-adapter", max_attempts=3,
        )
        counts = db.execute(sa.text(
            "SELECT (SELECT count(*) FROM inspection_report.reports WHERE is_formal),"
            "(SELECT count(*) FROM inspection_report.report_jobs)"
        )).one()
    assert replay["public_id"] == first["public_id"]
    assert counts == (1, 1)


def test_concurrent_same_report_idempotency_key_returns_one_resource(factory) -> None:
    actor, property_id, key = uuid4(), uuid4(), uuid4()
    barrier = threading.Barrier(2)
    resources = []

    def create():
        with factory() as db:
            barrier.wait()
            value = ReportRepository(db).create_report(
                actor, "staff", property_id, None, "Concurrent report", key,
                uuid4(), "deterministic-test-adapter",
            )
            resources.append(value["public_id"])

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(resources) == 2
    assert len(set(resources)) == 1
    with factory() as db:
        assert db.execute(sa.text(
            "SELECT count(*) FROM inspection_report.reports WHERE is_formal"
        )).scalar_one() == 1


def test_two_workers_claim_a_job_exactly_once(factory) -> None:
    report, actor, _ = create_report(factory)
    job = add_job(factory, report, actor, add_file(factory, report, actor))
    barrier = threading.Barrier(2)
    claimed = []

    def claim(worker):
        with factory() as db:
            barrier.wait()
            value = ReportRepository(db).claim(worker, 60)
            claimed.append(value["public_id"] if value else None)

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert claimed.count(job["public_id"]) == 1
    assert claimed.count(None) == 1


def test_heartbeat_expiry_recovers_and_persistent_events_remain_queryable(factory) -> None:
    report, actor, _ = create_report(factory)
    job = add_job(factory, report, actor, add_file(factory, report, actor))
    with factory() as db:
        repo = ReportRepository(db)
        claimed = repo.claim("crashed-worker", 60)
        assert repo.heartbeat(claimed["id"], "crashed-worker", 60, 25)
    with factory() as db, db.begin():
        db.execute(sa.text(
            "UPDATE inspection_report.report_jobs SET lease_until=:expired WHERE public_id=:id"
        ), {"expired": datetime.now(timezone.utc) - timedelta(seconds=1), "id": job["public_id"]})
    with factory() as db:
        repo = ReportRepository(db)
        assert repo.recover_stale() == 1
        recovered = repo.claim("replacement-worker", 60)
        assert recovered["public_id"] == job["public_id"]
    with factory() as db:
        events = ReportRepository(db).job_events(recovered["id"])
    assert [event["sequence_no"] for event in events] == list(range(1, len(events) + 1))
    assert {event["event_type"] for event in events} >= {"job.created", "job.started", "job.retry_wait"}


def test_retry_policy_and_safe_cancellation_are_durable(factory) -> None:
    report, actor, _ = create_report(factory)
    job = add_job(factory, report, actor, add_file(factory, report, actor))
    with factory() as db:
        repo = ReportRepository(db)
        claimed = repo.claim("worker", 60)
        assert repo.finish_failure(claimed, "temporary", True, "temporary") == "retry_wait"
        with db.begin():
            db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET available_at=NOW() WHERE public_id=:id"
            ), {"id": job["public_id"]})
        claimed = repo.claim("worker", 60)
        assert repo.finish_failure(claimed, "invalid_input", False, "invalid") == "failed"
    report2, actor2, _ = create_report(factory)
    queued = add_job(factory, report2, actor2, add_file(factory, report2, actor2))
    with factory() as db:
        repo = ReportRepository(db)
        cancelled = repo.request_cancel(queued, actor2, "user requested", uuid4(), uuid4())
    with factory() as db:
        persisted = ReportRepository(db).get_job(cancelled["public_id"])
        events = ReportRepository(db).job_events(persisted["id"])
    assert persisted["status"] == "cancelled"
    assert events[-1]["event_type"] == "job.cancelled"


def test_adapter_persists_existing_report_json_and_evidence_once(factory) -> None:
    report, actor, _ = create_report(factory)
    input_file = add_file(factory, report, actor)
    job = add_job(factory, report, actor, input_file)
    evidence_public = uuid4()
    with factory() as db, db.begin():
        db.execute(sa.text(
            "INSERT INTO inspection_report.files "
            "(public_id,created_by_subject_id,purpose,bucket,object_key,original_name,mime_type,file_size,sha256,status,scan_status,report_id) "
            "VALUES (:public,:actor,'evidence_image','private-test',:object,'evidence.jpg','image/jpeg',4,:sha,'ready','clean',:report)"
        ), {"public": evidence_public, "actor": actor, "object": f"evidence/{evidence_public.hex}",
             "sha": "b" * 64, "report": report["id"]})
    payload = {"title": "Pipeline title", "regions": [{"regionName": ["Kitchen"],
                "evidenceImages": [f"/api/assets/{evidence_public.hex}"]}]}
    with factory() as db:
        repo = ReportRepository(db)
        claimed = repo.claim("adapter-worker", 60)
        repo.persist_pipeline_result(
            claimed, payload, payload["regions"], [f"/api/assets/{evidence_public.hex}"], True,
        )
        assert repo.finish_success(claimed, {"report": payload, "validation": {"success": True}})
    with factory() as db:
        repo = ReportRepository(db)
        saved = repo.get_report(report["public_id"])
        assert saved["report_payload"] == payload
        assert saved["status"] == "active"
        assert repo.evidence_ids(saved["id"]) == [evidence_public]
        assert db.execute(sa.text(
            "SELECT count(*) FROM inspection_report.report_analysis WHERE report_id=:id"
        ), {"id": saved["id"]}).scalar_one() == 1


def test_crash_after_report_commit_recovers_without_failing_or_rerunning_report(factory) -> None:
    report, actor, _ = create_report(factory)
    job = add_job(factory, report, actor, add_file(factory, report, actor))
    payload = {"title": "Committed before crash", "regions": [{"regionName": ["Hall"]}]}
    with factory() as db:
        repo = ReportRepository(db)
        claimed = repo.claim("crashed-after-persist", 60)
        with db.begin():
            db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET max_attempts=1 WHERE id=:id"
            ), {"id": claimed["id"]})
        repo.persist_pipeline_result(claimed, payload, payload["regions"], [], True)
    with factory() as db, db.begin():
        db.execute(sa.text(
            "UPDATE inspection_report.report_jobs SET lease_until=NOW()-INTERVAL '1 second' WHERE public_id=:id"
        ), {"id": job["public_id"]})
    with factory() as db:
        repo = ReportRepository(db)
        assert repo.recover_stale() == 1
        recovered = repo.claim("recovery-worker", 60)
        assert recovered["report_status"] == "active"
        assert recovered["report_payload"] == payload
        assert recovered["attempt"] == 1
