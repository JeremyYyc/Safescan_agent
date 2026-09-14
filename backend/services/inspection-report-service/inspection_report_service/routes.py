import asyncio
import json
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
import sqlalchemy as sa
from sqlalchemy.orm import Session

from .auth import Principal, current_principal
from .clients import MaintenanceClient, PropertyLeasingClient
from .config import Settings, get_settings
from .database import get_db
from .errors import error, hidden_not_found
from .repository import ReportRepository
from .schemas import CancelJob, JobCreate, ReportCreate
from .service import ReportService
from .storage import minio_client


router = APIRouter(prefix="/internal/v1")
Actor = Annotated[Principal, Depends(current_principal)]
Db = Annotated[Session, Depends(get_db)]
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


@lru_cache(maxsize=1)
def leasing_client() -> PropertyLeasingClient:
    return PropertyLeasingClient(get_settings())


@lru_cache(maxsize=1)
def maintenance_client() -> MaintenanceClient:
    return MaintenanceClient(get_settings())


def service(db: Db) -> ReportService:
    return ReportService(db, leasing_client(), get_settings(), maintenance_client())


Service = Annotated[ReportService, Depends(service)]


def request_id(request: Request) -> UUID:
    try:
        return UUID(request.state.request_id)
    except (ValueError, AttributeError):
        from uuid import uuid4
        return uuid4()


def report_view(value: dict, repo: ReportRepository, tenant: bool = False) -> dict:
    body = {
        "id": value["public_id"], "property_id": value["property_id"],
        "source_lease_id": value.get("source_lease_id"), "title": value["title"],
        "source": value["source"], "status": value["status"], "version": value["version"],
        "completed_at": value.get("completed_at"), "validation_passed": value.get("validation_passed"),
        "can_download": False,
    }
    if value.get("status") == "active":
        body["report"] = value.get("report_payload") or {}
        body["region_info"] = value.get("region_info") or []
        body["evidence_images"] = repo.evidence_ids(value["id"])
    if tenant:
        body.pop("validation_passed", None)
        report = body.get("report")
        if isinstance(report, dict):
            body["report"] = {key: val for key, val in report.items()
                              if key not in {"validation", "workflowLog", "model", "provider"}}
    return jsonable_encoder(body)


def job_view(job: dict, repo: ReportRepository) -> dict:
    events = repo.job_events(job["id"])
    stage = events[-1]["stage"] if events else "queued"
    return jsonable_encoder({
        "id": job["public_id"], "type": job["job_type"], "status": job["status"],
        "stage": stage, "progress_percent": float(job["progress_percent"]),
        "attempt": job["attempt"], "max_attempts": job["max_attempts"],
        "report_id": job["report_public_id"],
        "error": {"code": job["error_code"], "retryable": job["status"] == "retry_wait"}
        if job.get("error_code") else None,
        "created_at": job["created_at"], "updated_at": job["updated_at"],
    })


@router.post("/properties/{property_id}/reports", status_code=status.HTTP_201_CREATED)
def create_report(property_id: UUID, payload: ReportCreate, actor: Actor, svc: Service,
                  key: IdempotencyKey, request: Request):
    result = svc.create_report(actor, property_id, payload.title, key, request_id(request))
    return report_view(result, svc.repo, tenant=actor.account_type == "customer")


@router.get("/properties/{property_id}/reports")
def property_reports(property_id: UUID, actor: Actor, svc: Service,
                     source_lease_id: UUID | None = None):
    values = svc.reports(actor, property_id, source_lease_id)
    return {"items": [report_view(value, svc.repo, tenant=actor.account_type == "customer") for value in values]}


@router.get("/reports")
def reports(property_id: UUID, actor: Actor, svc: Service, source_lease_id: UUID | None = None):
    return property_reports(property_id, actor, svc, source_lease_id)


@router.get("/reports/{report_id}")
def report(report_id: UUID, actor: Actor, svc: Service, lease_id: UUID | None = None):
    value = svc.report(actor, report_id, lease_context=lease_id)
    return report_view(value, svc.repo, tenant=actor.account_type == "customer")


@router.get("/reports/{report_id}/work-context")
def report_work_context(report_id: UUID, maintenance_order_id: UUID, actor: Actor, svc: Service):
    return jsonable_encoder(svc.work_context(actor, report_id, maintenance_order_id))


@router.post("/reports/{report_id}/files/videos", status_code=status.HTTP_201_CREATED)
async def upload_video(report_id: UUID, request: Request, actor: Actor, svc: Service,
                       key: IdempotencyKey,
                       x_file_name: Annotated[str, Header(alias="X-File-Name", max_length=255)],
                       x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None):
    value = await svc.upload_video(actor, report_id, request, x_file_name, x_content_sha256, key)
    return jsonable_encoder({"id": value["public_id"], "purpose": value["purpose"],
                             "mime_type": value["mime_type"], "file_size": value["file_size"],
                             "sha256": value["sha256"], "status": value["status"]})


@router.post("/reports/{report_id}/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(report_id: UUID, payload: JobCreate, actor: Actor, svc: Service, key: IdempotencyKey):
    value = svc.create_job(actor, report_id, payload.input_file_id, payload.attributes, key)
    return job_view(value, svc.repo)


@router.get("/report-jobs/{job_id}")
def get_job(job_id: UUID, actor: Actor, svc: Service, lease_id: UUID | None = None):
    value = svc.job(actor, job_id, lease_id)
    return {**job_view(value, svc.repo), "steps": jsonable_encoder(svc.repo.job_steps(value["id"]))}


@router.get("/report-jobs/{job_id}/events")
async def job_events(job_id: UUID, actor: Actor, svc: Service,
                     after_sequence: int = Query(0, ge=0), lease_id: UUID | None = None):
    job = svc.job(actor, job_id, lease_id)

    async def stream():
        sequence = after_sequence
        while True:
            events = svc.repo.job_events(job["id"], sequence)
            for event in events:
                sequence = int(event["sequence_no"])
                yield json.dumps(jsonable_encoder({
                    "sequence_no": sequence, "type": event["event_type"], "job_id": job["public_id"],
                    "stage": event["stage"], "progress_percent": event["progress_percent"],
                    "message": event["message"], "occurred_at": event["created_at"],
                }), ensure_ascii=False) + "\n"
            current = svc.repo.get_job(job["public_id"])
            if not current or current["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/report-jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_job(job_id: UUID, payload: CancelJob, actor: Actor, svc: Service,
               key: IdempotencyKey, request: Request):
    job = svc.job(actor, job_id)
    if job["requested_by_subject_id"] != actor.subject_id and not actor.has("report:generate_all"):
        raise hidden_not_found()
    value = svc.repo.request_cancel(job, actor.subject_id, payload.reason, key, request_id(request))
    return job_view(value, svc.repo)


@router.get("/files/{file_id}/content")
def file_content(file_id: UUID, actor: Actor, svc: Service, lease_id: UUID | None = None):
    value = svc.repo.get_file(file_id)
    if not value or not value.get("report_public_id") or value["status"] != "ready":
        raise hidden_not_found()
    svc.report(actor, value["report_public_id"], lease_context=lease_id)
    client = minio_client(
        svc.settings.minio_endpoint, svc.settings.minio_access_key.get_secret_value(),
        svc.settings.minio_secret_key.get_secret_value(), svc.settings.minio_secure,
    )

    def body():
        response = client.get_object(value["bucket"], value["object_key"])
        try:
            while chunk := response.read(svc.settings.upload_chunk_bytes):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(body(), media_type=value["mime_type"] or "application/octet-stream",
                             headers={"Cache-Control": "private, no-store"})


@router.get("/workers/health")
def worker_health(db: Db, _: Actor):
    row = db.execute(sa.text(
        "SELECT count(*) FILTER (WHERE status IN ('queued','retry_wait')) AS queue_depth,"
        "min(created_at) FILTER (WHERE status IN ('queued','retry_wait')) AS oldest_queued,"
        "count(*) FILTER (WHERE status='running' AND lease_until<NOW()) AS stale_lease "
        "FROM inspection_report.report_jobs"
    )).mappings().one()
    return jsonable_encoder(dict(row))
