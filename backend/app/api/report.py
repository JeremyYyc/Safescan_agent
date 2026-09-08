from app import storage
import asyncio
import json
import re
import threading
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field

from app.auth import require_user
from app.db import (
    chat_has_report,
    create_report_job,
    get_chat,
    get_latest_pdf_for_chat,
    get_report_job,
    get_report_job_events,
    get_report_job_steps,
    resolve_chat_internal_id,
    is_db_available,
)
from app.settings import get_settings

router = APIRouter()

def _resolve_user_video_asset(ref, current_user):
    try:
        row=storage.record(ref,current_user['user_id'])
        if not (row['mime_type'] or '').startswith('video/'):
            raise HTTPException(400,'Asset is not a video')
        return storage.asset_ref(ref)
    except (ValueError,FileNotFoundError):
        raise HTTPException(404,'Video asset not found')


class ProcessRequest(BaseModel):
    video_asset_id: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    chat_id: Optional[str] = None


def _normalize_report_for_pdf(report: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    normalized = dict(report)
    normalized.setdefault("meta", {})
    normalized.setdefault("regions", [])
    normalized.setdefault("scores", {})
    normalized.setdefault("top_risks", [])
    normalized.setdefault("recommendations", {})
    normalized.setdefault("comfort", {})
    normalized.setdefault("compliance", {})
    normalized.setdefault("action_plan", [])
    normalized.setdefault("limitations", [])
    return normalized


def _extract_report_preview_text(report: Dict[str, Any], limit: int = 6000) -> str:
    if not isinstance(report, dict):
        return ""
    parts = []
    title = report.get("title") or ""
    if title:
        parts.append(str(title))
    for section in ("top_risks", "limitations"):
        values = report.get(section)
        if isinstance(values, list):
            parts.extend([str(item) for item in values if str(item).strip()])
    text = "\n".join(parts)
    return text[:limit]


@router.post("/uploadVideo")
async def upload_video(request: Request, current_user: dict = Depends(require_user)):
    from app.workflow.upload_graph import upload_video as execute_upload
    return await execute_upload(request,current_user['user_id'])


@router.post("/processVideoStream")
def process_video_stream(
    payload: ProcessRequest, current_user: Dict[str, Any] = Depends(require_user)
) -> StreamingResponse:
    if not payload.video_asset_id:
        raise HTTPException(status_code=400, detail="video_asset_id is required")
    if payload.chat_id is None:
        raise HTTPException(status_code=400, detail="chat_id is required")
    internal_chat_id = resolve_chat_internal_id(payload.chat_id)
    if internal_chat_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat = get_chat(internal_chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat_has_report(internal_chat_id):
        raise HTTPException(
            status_code=409,
            detail="Report already exists for this chat. Create a new report to run another analysis.",
        )
    validated_video_asset_id = _resolve_user_video_asset(payload.video_asset_id, current_user)
    try:
        job = create_report_job(
            user_id=int(current_user["user_id"]),
            workspace_id=internal_chat_id,
            video_asset_id=validated_video_asset_id,
            attributes=payload.attributes or {},
            pipeline_version=get_settings().REPORT_PIPELINE_VERSION,
        )
    except Exception as exc:
        # The database partial unique index is the concurrency authority.
        if "uq_report_jobs_one_active_workspace" in str(exc) or "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Report generation is already in progress for this chat.")
        raise
    if not job:
        raise HTTPException(status_code=500, detail="Failed to create report job")

    if get_settings().REPORT_WORKER_INLINE:
        from app.workers.report_worker import run_job_until_terminal
        threading.Thread(target=run_job_until_terminal, args=(int(job["id"]),), daemon=True).start()

    async def event_stream():
        sequence = 0
        yield json.dumps({"type": "job", "job_id": job["job_id"], "status": job["status"]}, ensure_ascii=False) + "\n"
        while True:
            events = await asyncio.to_thread(get_report_job_events, int(job["id"]), sequence)
            for event in events:
                sequence = max(sequence, int(event["sequence_no"]))
                event_type = event["event_type"]
                payload_data = event.get("payload") or {}
                if event_type == "trace":
                    yield json.dumps({"type": "trace", "entry": payload_data.get("entry") or {}}, ensure_ascii=False) + "\n"
                elif event_type == "complete":
                    yield json.dumps({"type": "complete", "result": payload_data.get("result") or {}}, ensure_ascii=False) + "\n"
                elif event_type == "error":
                    error_event = {
                        "type": "error",
                        "code": payload_data.get("code"),
                        "message": event.get("message") or "报告生成失败",
                    }
                    # Preserve useful incomplete-video diagnostics while keeping
                    # arbitrary persisted metadata out of the public response.
                    if isinstance(payload_data.get("frameStats"), dict):
                        error_event["frameStats"] = payload_data["frameStats"]
                    yield json.dumps(error_event, ensure_ascii=False) + "\n"
                elif event_type == "retry":
                    yield json.dumps({"type": "status", "status": "retry_wait", "message": event.get("message")}, ensure_ascii=False) + "\n"
            current = await asyncio.to_thread(get_report_job, int(job["id"]))
            if not current or current["status"] in ("completed", "failed", "cancelled"):
                yield json.dumps({"type": "end", "job_id": job["job_id"], "status": current["status"] if current else "missing"}, ensure_ascii=False) + "\n"
                break
            await asyncio.sleep(get_settings().REPORT_JOB_EVENT_POLL_SECONDS)

    return StreamingResponse(event_stream(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@router.get("/report-jobs/{job_id}")
def get_report_job_status(job_id: str, current_user: Dict[str, Any] = Depends(require_user)) -> JSONResponse:
    job = get_report_job(job_id)
    if not job or int(job["user_id"]) != int(current_user["user_id"]):
        raise HTTPException(status_code=404, detail="Report job not found")
    events = get_report_job_events(int(job["id"]), 0)
    steps = get_report_job_steps(int(job["id"]))
    return JSONResponse(jsonable_encoder({"job": job, "steps": steps, "events": events}))

@router.post("/reports/{chat_id}/export-pdf")
def export_report_pdf(
    chat_id: str, current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    from app.workflow.pdf_graph import export_pdf
    return JSONResponse(export_pdf(chat_id,current_user['user_id']))


@router.get("/reports/{chat_id}/pdf-latest")
def get_latest_report_pdf(
    chat_id: str, current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id = resolve_chat_internal_id(chat_id)
    if internal_chat_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat = get_chat(internal_chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")

    latest = get_latest_pdf_for_chat(internal_chat_id)
    if not latest:
        return JSONResponse({"pdf": None})

    source_path = latest.get("source_path")
    pdf_url = source_path or ""
    created_at = latest.get("created_at")
    created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
    return JSONResponse(
        {
            "pdf": {
                "report_id": latest.get("report_id"),
                "pdf_url": pdf_url,
                "download_url": f"/api/reports/pdf/{latest.get('report_id')}/download",
                "created_at": created_at_str,
            }
        }
    )


@router.get("/reports/pdf/{report_id}/download")
def download_report_pdf(
    report_id: str, current_user: Dict[str, Any] = Depends(require_user)
) -> Response:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    from app.db import get_report_by_public_id
    report = get_report_by_public_id(report_id)
    if not report or report.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("source_type") != "pdf":
        raise HTTPException(status_code=400, detail="Report is not a PDF")
    source_path = report.get("source_path")
    if not source_path:
        raise HTTPException(status_code=404, detail="PDF source missing")
    try:
        data = storage.read(source_path,current_user['user_id'])
    except FileNotFoundError:
        raise HTTPException(404,'PDF file not found')
    report_meta = report.get("report_json")
    title_hint = ""
    if isinstance(report_meta, dict):
        title_hint = str(report_meta.get("title") or "").strip()
    if not title_hint:
        title_hint = f"Report {report_id}"
    safe = re.sub(r"[\\\\/:*?\"<>|]+", "_", title_hint).strip()
    safe = re.sub(r"\s+", " ", safe)
    filename = f"{safe or f'report_{report_id}'}.pdf"
    return Response(data,media_type="application/pdf",headers={"Content-Disposition":f"attachment; filename=report.pdf; filename*=UTF-8''{quote(filename)}","Cache-Control":"private, no-store"})
