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
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.auth import require_user
from app.db import chat_has_report, get_chat, update_chat_title
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
    chat_id: Optional[int] = None


@router.post("/uploadVideo")
async def upload_video(
    file: UploadFile = File(...), current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")

    target_dir = OUTPUT_DIR / "videos"
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
    chat = get_chat(payload.chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat_has_report(payload.chat_id):
        raise HTTPException(
            status_code=409,
            detail="Report already exists for this chat. Create a new report to run another analysis.",
        )
    if not _acquire_processing(payload.chat_id):
        raise HTTPException(
            status_code=409,
            detail="Report generation is already in progress for this chat.",
        )

    event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    run_dir = OUTPUT_DIR / f"run_{uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        print(msg, flush=True)

    def emit_trace(entry: Dict[str, Any]) -> None:
        step = entry.get("step", "trace")
        details = entry.get("details", {})
        log(f"[TRACE] {step}: {details}")
        event_queue.put({"type": "trace", "entry": entry})

    user_id = current_user.get("user_id")
    chat_id = payload.chat_id

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
                video_path=payload.video_path,
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
                            "video_path": payload.video_path,
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
                            "video_path": payload.video_path,
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
                "video_path": payload.video_path,
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
                        payload.video_path,
                        report_data=final_report if isinstance(final_report, dict) else None,
                        representative_images=state.representative_images,
                        chat_id=payload.chat_id,
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
