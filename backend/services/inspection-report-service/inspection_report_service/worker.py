import logging
import os
import socket
import time
from threading import Event

from app.report_errors import ReportGenerationError, require_report_content
from app.workflow.graph import WorkflowCancelled
from app.workflow.orchestrator import WorkflowOrchestrator, result_payload

from .config import get_settings
from .database import get_session_factory
from .pipeline_adapter import ReportPipelineServices
from .repository import ReportRepository
from .storage import PipelineStorage, asset_ref


logger = logging.getLogger(__name__)

PROGRESS = {
    "authorize_complete": 5, "extract_complete": 18, "filter_complete": 28,
    "select_complete": 38, "detect_complete": 48, "scene_complete": 58,
    "router_complete": 63, "hazard_complete": 70, "comfort_complete": 72,
    "compliance_complete": 77, "scoring_complete": 80,
    "recommendations_complete": 85, "write_complete": 90,
    "validate_complete": 93, "repair_complete": 93, "evidence_complete": 96,
    "title_complete": 97, "persist_complete": 99,
}


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def execute(job: dict, worker_id: str) -> str:
    settings = get_settings()
    with get_session_factory()() as db:
        repo = ReportRepository(db)
        storage = PipelineStorage(settings, job["report_id"], job["report_public_id"], job["report_creator"])
        services = ReportPipelineServices(repo, job, storage)
        cancel = Event()

        # A worker may crash after the report transaction commits but before the
        # job completion transaction commits. Recovery must not rerun the video
        # pipeline or create duplicate evidence/PDF objects in that window.
        if job.get("report_status") == "active" and job.get("report_payload"):
            result = {
                "regionInfo": job.get("region_info") or [],
                "report": job["report_payload"],
                "representativeImages": [asset_ref(value) for value in repo.evidence_ids(job["report_id"])],
                "video_asset_id": asset_ref(job["file_public_id"]),
                "validation": {"success": bool(job.get("report_validation_passed")), "iterations": 0},
                "report_id": job["report_id"],
            }
            return "completed" if repo.finish_success(job, result) else "lost"

        def trace(entry: dict) -> None:
            step = str(entry.get("step") or "workflow")
            progress = PROGRESS.get(step)
            if repo.is_cancel_requested(job["id"]):
                cancel.set()
            if not repo.heartbeat(job["id"], worker_id, settings.worker_lease_seconds, progress):
                cancel.set()
                raise WorkflowCancelled("Worker lease was lost")
            repo.record_step(job["id"], job["attempt"], step, entry.get("details") or {})
            repo.append_event(job["id"], "step.progress", step, progress, None, {})

        try:
            state = WorkflowOrchestrator(services=services).execute_workflow(
                asset_ref(job["file_public_id"]),
                (job.get("input_payload") or {}).get("attributes", {}),
                user_id=job["id"], chat_id=job["report_id"], trace_cb=trace, cancel=cancel,
            )
            result = result_payload(state)
            if cancel.is_set():
                repo.finish_cancelled(job)
                return "cancelled"
            if state.get("warning"):
                return repo.finish_failure(job, "report_generation_failed", False, "Video did not produce a report")
            require_report_content(state.get("draft_report"))
            if not state.get("report_id"):
                raise ReportGenerationError("Report persistence did not complete")
            if not repo.finish_success(job, result):
                raise RuntimeError("Job completion ownership was lost")
            return "completed"
        except WorkflowCancelled:
            if repo.is_cancel_requested(job["id"]):
                repo.finish_cancelled(job)
                return "cancelled"
            return repo.finish_failure(job, "worker_lease_expired", True, "Worker lease was lost")
        except (ReportGenerationError, ValueError, PermissionError, FileNotFoundError) as exc:
            logger.warning("Deterministic report failure job=%s type=%s", job["public_id"], type(exc).__name__)
            return repo.finish_failure(job, "report_generation_failed", False, "Report input or output was invalid")
        except Exception:
            logger.exception("Transient report worker failure job=%s", job["public_id"])
            return repo.finish_failure(job, "report_worker_failed", True, "Temporary report processing failure")


def process_one(worker_id: str | None = None) -> bool:
    settings = get_settings()
    worker_id = worker_id or worker_identity()
    with get_session_factory()() as db:
        repo = ReportRepository(db)
        repo.recover_stale()
        job = repo.claim(worker_id, settings.worker_lease_seconds)
    if not job:
        return False
    execute(job, worker_id)
    return True


def run_forever() -> None:
    settings = get_settings()
    worker_id = worker_identity()
    logger.info("Inspection report worker started worker_id=%s", worker_id)
    while True:
        if not process_one(worker_id):
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
