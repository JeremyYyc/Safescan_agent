from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

from inspection_report_service import worker


class FakeRepo:
    failure = None
    success = None

    def __init__(self, db):
        pass

    def is_cancel_requested(self, job_id):
        return False

    def heartbeat(self, *args):
        return True

    def record_step(self, *args):
        pass

    def append_event(self, *args):
        pass

    def evidence_ids(self, report_id):
        return []

    def finish_success(self, job, result):
        type(self).success = result
        return True

    def finish_failure(self, job, code, retryable, message):
        type(self).failure = (code, retryable)
        return "retry_wait" if retryable else "failed"

    def finish_cancelled(self, job):
        pass


def job(**values):
    base = {
        "id": 1, "public_id": uuid4(), "report_id": 2, "report_public_id": uuid4(),
        "report_creator": uuid4(), "file_public_id": uuid4(), "attempt": 1,
        "worker_id": "worker", "input_payload": {}, "progress_percent": 1,
        "report_status": "processing", "report_payload": None,
    }
    return {**base, **values}


def arrange(monkeypatch, outcome):
    FakeRepo.failure = FakeRepo.success = None
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(worker_lease_seconds=60))
    monkeypatch.setattr(worker, "get_session_factory", lambda: lambda: nullcontext(object()))
    monkeypatch.setattr(worker, "ReportRepository", FakeRepo)
    monkeypatch.setattr(worker, "PipelineStorage", lambda *args: object())
    monkeypatch.setattr(worker, "ReportPipelineServices", lambda *args: object())
    monkeypatch.setattr(worker.WorkflowOrchestrator, "execute_workflow", outcome)


def test_deterministic_pipeline_failure_is_not_retried(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise ValueError("invalid input")

    arrange(monkeypatch, fail)
    assert worker.execute(job(), "worker") == "failed"
    assert FakeRepo.failure == ("report_generation_failed", False)


def test_unexpected_pipeline_failure_is_bounded_retry_candidate(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("temporary object-store failure")

    arrange(monkeypatch, fail)
    assert worker.execute(job(), "worker") == "retry_wait"
    assert FakeRepo.failure == ("report_worker_failed", True)


def test_restart_after_report_commit_does_not_rerun_pipeline(monkeypatch) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("pipeline reran after committed report")

    arrange(monkeypatch, must_not_run)
    report_payload = {"title": "Already persisted", "regions": [{"regionName": ["Kitchen"]}]}
    result = worker.execute(job(
        report_status="active", report_payload=report_payload, region_info=[],
        report_validation_passed=True,
    ), "worker")
    assert result == "completed"
    assert FakeRepo.success["report"] == report_payload
