from io import BytesIO
from starlette.concurrency import run_in_threadpool
from app import storage
from app.api.assets import read_upload
import asyncio
import json
import queue
import re
import threading
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field

from app.auth import require_user
from app.agents.report_pdf_agent import ReportPdfRepairAgent
from app.pdf.report_pdf import render_report_pdf
from app.db import (
    chat_has_report,
    ensure_user_storage_uuid,
    get_chat,
    get_latest_report_id,
    get_latest_pdf_for_chat,
    get_latest_report_assets,
    get_report,
    add_chat_report_ref,
    resolve_chat_internal_id,
    store_pdf_report,
    update_chat_title,
    is_db_available,
)
from app.settings import get_settings

router = APIRouter()

_processing_lock = threading.Lock()
_processing_chats: set[int] = set()


def _resolve_user_video_asset(ref, current_user):
    try:
        row=storage.record(ref,current_user['user_id'])
        if not (row['mime_type'] or '').startswith('video/'):
            raise HTTPException(400,'Asset is not a video')
        return storage.asset_ref(ref)
    except (ValueError,FileNotFoundError):
        raise HTTPException(404,'Video asset not found')


def _acquire_processing(chat_id: int) -> bool:
    with _processing_lock:
        if len(_processing_chats) >= get_settings().VIDEO_WORKER_CONCURRENCY:
            return False
        if chat_id in _processing_chats:
            return False
        _processing_chats.add(chat_id)
        return True


def _release_processing(chat_id: int) -> None:
    with _processing_lock:
        _processing_chats.discard(chat_id)


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
    mime=request.headers.get('content-type','').split(';')[0]
    if not mime.startswith('video/'):
        raise HTTPException(400,'Send raw video bytes with a video Content-Type')
    data=await read_upload(request)
    ref=await run_in_threadpool(storage.put,data,mime,user_id=current_user['user_id'],category='media')
    return {'video_asset_id':ref}


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
    if not _acquire_processing(internal_chat_id):
        raise HTTPException(
            status_code=409,
            detail="Report generation is already in progress for this chat.",
        )


    event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    def log(msg: str) -> None:
        print(msg, flush=True)

    def emit_trace(entry: Dict[str, Any]) -> None:
        step = entry.get("step", "trace")
        details = entry.get("details", {})
        log(f"[TRACE] {step}: {details}")
        event_queue.put({"type": "trace", "entry": entry})

    user_id = current_user.get("user_id")
    chat_id = internal_chat_id

    def worker() -> None:
        try:
            from app.agents.report_writer_agent import ReportWriterAgent
            from app.agents.title_agent import TitleAgent
            from app.agents.validator_agent import ValidatorAgent
            from app.db import add_chat_report_detail, store_report
            from app.workflow.orchestrator import WorkflowOrchestrator
            from app.workflow.react_loop import ReactRepairLoop

            workflow_orchestrator = WorkflowOrchestrator()
            attributes = payload.attributes or {}

            log("[WORKFLOW] start execute_workflow")
            state = workflow_orchestrator.execute_workflow(
                video_asset_id=str(validated_video_asset_id),
                user_attributes=attributes,
                trace_cb=emit_trace,
                run_agents=True,
            )
            log(f"[WORKFLOW] complete execute_workflow: images={len(state.representative_images)}")
            log("------------------------------------------------------------------------------------")

            if not state.representative_images:
                log("[WORKFLOW] no representative images generated")
                event_queue.put(
                    {
                        "type": "complete",
                        "result": {
                            "regionInfo": [{"warning": ["No representative images generated"]}],
                            "representativeImages": [],
                            "video_asset_id": str(validated_video_asset_id),
                            "workflowLog": state.trace_log,
                        },
                    }
                )
                return

            report_writer_agent = ReportWriterAgent()
            validator_agent = ValidatorAgent({"config_list": []})
            react_loop = ReactRepairLoop(validator_agent, report_writer_agent)

            region_evidence = state.region_evidence or []
            hazards = state.hazards or []
            comfort_result = state.comfort or {}
            compliance_result = state.compliance or {}
            scoring_result = state.scoring or {}
            recommendations_result = state.recommendations or {}
            draft_report = state.draft_report or {}

            if not region_evidence:
                log("[WORKFLOW] no region evidence generated")
                event_queue.put(
                    {
                        "type": "complete",
                        "result": {
                            "regionInfo": [{"warning": ["No region evidence generated"]}],
                            "representativeImages": state.representative_images,
                            "video_asset_id": str(validated_video_asset_id),
                            "workflowLog": state.trace_log,
                        },
                    }
                )
                return

            state.add_trace("report_writer_start", {"region_count": len(region_evidence)})
            log("[REPORT] received draft report from orchestrator")
            draft_regions = 0
            if isinstance(draft_report, dict):
                draft_regions = len(draft_report.get("regions", []))
            state.add_trace(
                "report_writer_complete",
                {
                    "has_error": isinstance(draft_report, dict)
                    and "error" in draft_report,
                    "region_count": draft_regions,
                },
            )
            log(f"[REPORT] complete write_report: regions={draft_regions}")
            if isinstance(draft_report, dict) and "error" in draft_report:
                error_text = str(draft_report.get("error", ""))
                raw_text = str(draft_report.get("raw_response", ""))
                if error_text:
                    log(f"[REPORT_ERROR] {error_text}")
                if raw_text:
                    log(f"[REPORT_RAW] {raw_text[:1000]}")
            log("------------------------------------------------------------------------------------")

            state.add_trace("react_loop_start", {"max_iterations": 3})
            log("[REACT] start execute_repair_loop")
            final_report, success, iterations = react_loop.execute_repair_loop(
                draft_report,
                region_evidence,
                hazards,
                attributes,
                scoring_result,
                comfort_result,
                compliance_result,
                recommendations_result,
                trace_cb=state.add_trace,
            )
            state.add_trace(
                "react_loop_complete", {"success": success, "iterations": iterations}
            )
            log(f"[REACT] complete execute_repair_loop: success={success} iterations={iterations}")
            log("------------------------------------------------------------------------------------")

            state.draft_report = final_report
            state.validation = {"success": success, "iterations": iterations}

            region_info = []
            if isinstance(final_report, dict):
                region_info = final_report.get("regions", []) or []

            if isinstance(region_info, list) and region_evidence:
                def _region_key(value: str) -> str:
                    return re.sub(r"[_\\s]+", " ", str(value)).strip().lower()

                evidence_map = {}
                for entry in region_evidence:
                    label = entry.get("region_label")
                    if not label:
                        continue
                    key = _region_key(label)
                    images = entry.get("image_paths") or []
                    if isinstance(images, list):
                        evidence_map[key] = images

                for idx, region in enumerate(region_info):
                    if not isinstance(region, dict):
                        continue
                    names = region.get("regionName")
                    candidate_keys = []
                    if isinstance(names, list):
                        candidate_keys = [_region_key(name) for name in names if name]
                    elif isinstance(names, str) and names.strip():
                        candidate_keys = [_region_key(names)]
                    matched_images = []
                    for key in candidate_keys:
                        if key in evidence_map:
                            matched_images = evidence_map[key]
                            break
                    if matched_images:
                        region["evidenceImages"] = matched_images
                    elif idx < len(region_evidence):
                        fallback_images = region_evidence[idx].get("image_paths") or []
                        if isinstance(fallback_images, list) and fallback_images:
                            region["evidenceImages"] = fallback_images

            result_payload = {
                "regionInfo": region_info,
                "report": final_report if isinstance(final_report, dict) else {},
                "representativeImages": state.representative_images,
                "video_asset_id": str(validated_video_asset_id),
                "workflowLog": state.trace_log,
            }
            if isinstance(final_report, dict) and chat_id:
                try:
                    chat_snapshot = get_chat(chat_id)
                    if chat_snapshot and (not chat_snapshot.get("title") or chat_snapshot.get("title") == "New Chat"):
                        title_agent = TitleAgent()
                        new_title = title_agent.summarize_title(final_report)
                        if isinstance(new_title, str) and new_title.strip():
                            update_chat_title(chat_id, new_title.strip()[:255])
                            log(f"[CHAT] title updated: {new_title.strip()[:80]}")
                except Exception as exc:
                    log(f"[CHAT] title update failed: {exc}")
            if isinstance(final_report, dict):
                try:
                    report_id = store_report(
                        result_payload["regionInfo"],
                        str(validated_video_asset_id),
                        report_data=final_report if isinstance(final_report, dict) else None,
                        representative_images=state.representative_images,
                        chat_id=internal_chat_id,
                        user_id=user_id,
                    )
                    if chat_id and report_id:
                        add_chat_report_detail(chat_id, report_id, user_id=user_id)
                    log("[DB] store_report complete")
                except Exception as exc:
                    print(f"[DB] Failed to store report: {exc}", flush=True)

            event_queue.put({"type": "complete", "result": result_payload})
        except Exception as exc:
            log(f"[ERROR] worker failed: {exc}")
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            _release_processing(chat_id)
            log("[WORKFLOW] end")
            event_queue.put({"type": "end"})

    def scoped_worker():
        with storage.media_scope(user_id):
            worker()
    threading.Thread(target=scoped_worker, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        while True:
            event = await loop.run_in_executor(None, event_queue.get)
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event.get("type") == "end":
                break

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/reports/{chat_id}/export-pdf")
def export_report_pdf(
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

    assets = get_latest_report_assets(internal_chat_id) or {}
    report_json = assets.get("report_json")
    if not isinstance(report_json, dict) or not report_json:
        raise HTTPException(status_code=404, detail="Report data not found")

    report = _normalize_report_for_pdf(report_json)
    repair_agent = ReportPdfRepairAgent()
    repaired = repair_agent.repair_report(report)
    if isinstance(repaired, dict):
        report = _normalize_report_for_pdf(repaired)

    buffer = BytesIO()
    try:
        render_report_pdf(report, buffer)
        target_path=storage.put(buffer.getvalue(),'application/pdf',user_id=current_user['user_id'],category='reports')
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to render or store PDF") from exc

    title = (chat.get("title") or "").strip() or report.get("title") or f"Report {internal_chat_id}"
    preview = _extract_report_preview_text(report)
    derived_report_id = get_latest_report_id(internal_chat_id)
    from app.persistence.database import get_connection
    try:
        with get_connection():
            report_id = store_pdf_report(
                user_id=int(current_user['user_id']), source_path=target_path,
                title=str(title), extracted_text=preview, origin_chat_id=internal_chat_id,
                pdf_kind='exported', derived_from_report_id=derived_report_id)
            if not report_id: raise RuntimeError('Failed to store PDF metadata')
            add_chat_report_ref(internal_chat_id, report_id, source_chat_id=internal_chat_id, status='active')
    except BaseException:
        storage.remove_unreferenced(target_path,current_user['user_id'])
        raise

    return JSONResponse(
        {
            "report_id": report_id,
            "pdf_url": target_path,
            "download_url": f"/api/reports/pdf/{report_id}/download",
        }
    )


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
    return Response(data,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=report.pdf","Cache-Control":"private, no-store"})
