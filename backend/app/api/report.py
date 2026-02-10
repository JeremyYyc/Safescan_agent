import asyncio
import json
import os
import queue
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from app.auth import require_user
from app.agents.report_pdf_agent import ReportPdfRepairAgent
from app.pdf.report_pdf import render_report_pdf
from app.db import (
    chat_has_report,
    ensure_user_storage_uuid,
    get_chat,
    get_latest_pdf_for_chat,
    get_latest_report_assets,
    get_report,
    add_chat_report_ref,
    resolve_chat_internal_id,
    store_pdf_report,
    update_chat_title,
    is_db_available,
)
from app.env import load_env

BASE_DIR = Path(__file__).resolve().parents[2]
load_env()
output_dir_env = os.getenv("OUTPUT_DIR")
if output_dir_env:
    output_dir_path = Path(output_dir_env)
    if not output_dir_path.is_absolute():
        output_dir_path = (BASE_DIR / output_dir_path).resolve()
else:
    output_dir_path = BASE_DIR / "uploads"

OUTPUT_DIR = output_dir_path
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

_processing_lock = threading.Lock()
_processing_chats: set[int] = set()


def _get_user_storage_root(current_user: Dict[str, Any]) -> Path:
    user_id_raw = current_user.get("user_id")
    if not user_id_raw:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = int(user_id_raw)
    storage_uuid = str(current_user.get("storage_uuid") or "").strip()
    if not storage_uuid:
        storage_uuid = ensure_user_storage_uuid(user_id) or ""
    if not storage_uuid:
        raise HTTPException(status_code=500, detail="Failed to resolve user storage")
    root = OUTPUT_DIR / storage_uuid
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_user_video_path(raw_path: str, user_storage_root: Path) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()
    user_videos_dir = (user_storage_root / "Videos").resolve()
    if user_videos_dir not in candidate.parents:
        raise HTTPException(status_code=403, detail="video_path does not belong to current user")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="video_path not found")
    return candidate


def _acquire_processing(chat_id: int) -> bool:
    with _processing_lock:
        if chat_id in _processing_chats:
            return False
        _processing_chats.add(chat_id)
        return True


def _release_processing(chat_id: int) -> None:
    with _processing_lock:
        _processing_chats.discard(chat_id)


class ProcessRequest(BaseModel):
    video_path: str
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


def _build_public_upload_url(path: Path) -> str:
    try:
        rel = path.relative_to(OUTPUT_DIR)
        return f"/uploads/{rel.as_posix()}"
    except Exception:
        return ""


@router.post("/uploadVideo")
async def upload_video(
    file: UploadFile = File(...), current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")

    user_storage_root = _get_user_storage_root(current_user)
    target_dir = user_storage_root / "Videos" / "originals"
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".mp4"
    target_path = target_dir / f"{uuid4().hex}{suffix}"

    try:
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    return JSONResponse(
        {
            "video_path": str(target_path),
            "filename": file.filename,
        }
    )


@router.post("/processVideoStream")
async def process_video_stream(
    payload: ProcessRequest, current_user: Dict[str, Any] = Depends(require_user)
) -> StreamingResponse:
    if not payload.video_path:
        raise HTTPException(status_code=400, detail="video_path is required")
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
    if not _acquire_processing(internal_chat_id):
        raise HTTPException(
            status_code=409,
            detail="Report generation is already in progress for this chat.",
        )

    user_storage_root = _get_user_storage_root(current_user)
    validated_video_path = _resolve_user_video_path(payload.video_path, user_storage_root)

    event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    run_dir = user_storage_root / "Videos" / f"run_{uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=True)

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
                video_path=str(validated_video_path),
                user_attributes=attributes,
                extract_dir=str(run_dir),
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
                            "video_path": str(validated_video_path),
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
                            "video_path": str(validated_video_path),
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
                "video_path": str(validated_video_path),
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
                        str(validated_video_path),
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

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        while True:
            event = await loop.run_in_executor(None, event_queue.get)
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event.get("type") == "end":
                break

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/reports/{chat_id}/export-pdf")
async def export_report_pdf(
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

    user_storage_root = _get_user_storage_root(current_user)
    pdf_dir = user_storage_root / "PDF" / "generated"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    target_path = pdf_dir / f"report_{internal_chat_id}_{uuid4().hex}.pdf"

    try:
        render_report_pdf(report, target_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to render PDF: {str(exc)}")

    title = (chat.get("title") or "").strip() or report.get("title") or f"Report {internal_chat_id}"
    preview = _extract_report_preview_text(report)
    report_id = store_pdf_report(
        user_id=int(current_user.get("user_id")),
        source_path=str(target_path),
        title=str(title),
        extracted_text=preview,
    )
    if not report_id:
        try:
            target_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to store PDF report")

    add_chat_report_ref(internal_chat_id, report_id, source_chat_id=internal_chat_id, status="active")

    return JSONResponse(
        {
            "report_id": report_id,
            "pdf_url": _build_public_upload_url(target_path),
            "download_url": f"/api/reports/pdf/{report_id}/download",
        }
    )


@router.get("/reports/{chat_id}/pdf-latest")
async def get_latest_report_pdf(
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
    pdf_url = _build_public_upload_url(Path(source_path)) if source_path else ""
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
async def download_report_pdf(
    report_id: int, current_user: Dict[str, Any] = Depends(require_user)
) -> FileResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    report = get_report(report_id)
    if not report or report.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("source_type") != "pdf":
        raise HTTPException(status_code=400, detail="Report is not a PDF")
    source_path = report.get("source_path")
    if not source_path:
        raise HTTPException(status_code=404, detail="PDF source missing")
    path = Path(source_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    report_meta = report.get("report_json")
    title_hint = ""
    if isinstance(report_meta, dict):
        title_hint = str(report_meta.get("title") or "").strip()
    if not title_hint:
        title_hint = f"Report {report_id}"
    safe = re.sub(r"[\\\\/:*?\"<>|]+", "_", title_hint).strip()
    safe = re.sub(r"\s+", " ", safe)
    filename = f"{safe or f'report_{report_id}'}.pdf"
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=filename,
    )
