"""Durable worker for LangGraph video-report jobs."""
from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any, Dict, Optional

from app import db
from app.report_errors import ReportGenerationError, require_report_content
from app.settings import get_settings

logger = logging.getLogger(__name__)

_PROGRESS = {
    "authorize_complete": 5,
    "extract_complete": 18,
    "filter_complete": 28,
    "select_complete": 38,
    "detect_complete": 48,
    "scene_complete": 58,
    "router_complete": 63,
    "hazard_complete": 70,
    "comfort_complete": 72,
    "compliance_complete": 77,
    "scoring_complete": 80,
    "recommendations_complete": 85,
    "write_complete": 90,
    "validate_complete": 93,
    "repair_complete": 93,
    "evidence_complete": 96,
    "title_complete": 97,
    "persist_complete": 99,
}


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _recovered_result(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    report_id = job.get("report_id")
    report = db.get_report(int(report_id)) if report_id else None
    if not report or report.get("status") != "active":
        return None
    return {
        "run_id": f"recovered-job-{job['job_id']}",
        "regionInfo": report.get("region_info") or [],
        "report": report.get("report_json") or {},
        "representativeImages": report.get("representative_images") or [],
        "video_asset_id": report.get("video_asset_id"),
        "workflowLog": [],
        "validation": {"success": bool(report.get("validation_passed", True)), "iterations": 0},
        "report_id": report.get("report_id"),
        "warning": None,
        "frameStats": {"extracted": 0, "retained": 0, "representative": len(report.get("representative_images") or []), "rejected": {}},
    }


def execute_claimed_job(job: Dict[str, Any], worker_id: str) -> str:
    """Execute one claimed job and leave a durable terminal/retry state."""
    from app.workflow.orchestrator import WorkflowOrchestrator, result_payload

    settings = get_settings()
    job_id = int(job["id"])
    recovered = _recovered_result(job)
    if recovered:
        db.complete_report_job(job_id, recovered)
        return "completed"

    def trace(entry: Dict[str, Any]) -> None:
        step = str(entry.get("step") or "workflow")
        progress = _PROGRESS.get(step)
        db.heartbeat_report_job(job_id, worker_id, settings.REPORT_JOB_LEASE_SECONDS, progress)
        db.record_report_job_step(job_id, int(job["attempt"]), step, entry.get("details") or {})
        db.append_report_job_event(job_id, "trace", step, progress, None, {"entry": entry})

    try:
        state = WorkflowOrchestrator().execute_workflow(
            job["video_asset_id"],
            (job.get("input_payload") or {}).get("attributes") or {},
            user_id=int(job["user_id"]),
            chat_id=int(job["workspace_id"]),
            job_id=job_id,
            trace_cb=trace,
        )
        result = result_payload(state)
        if state.get("warning"):
            db.fail_report_job(job_id, "workflow_incomplete", str(state["warning"]), retry=False)
            return "failed"
        require_report_content(state.get("draft_report"))
        if not state.get("report_id"):
            raise ReportGenerationError("Report persistence did not complete. Please retry.")
        db.complete_report_job(job_id, result)
        return "completed"
    except ReportGenerationError as exc:
        logger.warning("Report job %s rejected: %s", job_id, exc)
        return db.fail_report_job(job_id, "report_generation_failed", str(exc), retry=False)
    except Exception as exc:
        logger.exception("Report job %s failed", job_id)
        return db.fail_report_job(job_id, "report_worker_failed", "报告生成失败，分析流程未成功完成", retry=True)


def process_one(worker_id: Optional[str] = None, job_id: Optional[int] = None) -> bool:
    settings = get_settings()
    worker_id = worker_id or worker_identity()
    db.recover_stale_report_jobs()
    job = db.claim_report_job(worker_id, settings.REPORT_JOB_LEASE_SECONDS, job_id=job_id)
    if not job:
        return False
    execute_claimed_job(job, worker_id)
    return True


def run_job_until_terminal(job_id: int) -> None:
    """Development/test runner; persistence is still the database job record."""
    settings = get_settings()
    worker_id = worker_identity() + ":inline"
    while True:
        job = db.get_report_job(job_id)
        if not job or job["status"] in ("completed", "failed", "cancelled"):
            return
        if not process_one(worker_id, job_id):
            time.sleep(settings.REPORT_JOB_POLL_SECONDS)


def run_forever() -> None:
    settings = get_settings()
    worker_id = worker_identity()
    logger.info("Report worker started worker_id=%s", worker_id)
    idle_delay = settings.REPORT_JOB_POLL_SECONDS
    while True:
        if process_one(worker_id):
            idle_delay = settings.REPORT_JOB_POLL_SECONDS
            continue
        time.sleep(idle_delay)
        idle_delay = min(5.0, idle_delay * 1.5)


if __name__ == "__main__":
    logging.basicConfig(level=get_settings().APP_LOG_LEVEL)
    run_forever()
