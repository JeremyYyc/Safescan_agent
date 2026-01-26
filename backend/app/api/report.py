import asyncio
import json
import queue
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.auth import require_user
from app.db import get_chat

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "uploads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


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
            from app.agents.scene_agent import SceneUnderstandingAgent
            from app.agents.hazard_agent import SafetyHazardAgent
            from app.agents.report_writer_agent import ReportWriterAgent
            from app.agents.validator_agent import ValidatorAgent
            from app.db import add_chat_message, store_report
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
            )
            log(f"[WORKFLOW] complete execute_workflow: images={len(state.representative_images)}")

            if not state.representative_images:
                log("[WORKFLOW] no representative images generated")
                event_queue.put(
                    {
                        "type": "complete",
                        "result": {
                            "regionInfo": [{"warning": ["No representative images generated"]}],
                            "representativeImages": [],
                            "workflowLog": state.trace_log,
                        },
                    }
                )
                return

            scene_agent = SceneUnderstandingAgent()
            hazard_agent = SafetyHazardAgent()
            report_writer_agent = ReportWriterAgent()
            validator_agent = ValidatorAgent({"config_list": []})
            react_loop = ReactRepairLoop(validator_agent, report_writer_agent)

            state.add_trace(
                "agent_pipeline_start",
                {"representative_image_count": len(state.representative_images)},
            )

            state.add_trace(
                "scene_agent_start", {"image_count": len(state.representative_images)}
            )
            log("[SCENE] start analyze_scene")
            region_evidence = scene_agent.analyze_scene(
                state.representative_images, attributes
            )
            state.region_evidence = region_evidence
            state.add_trace(
                "scene_agent_complete", {"region_count": len(region_evidence)}
            )
            log(f"[SCENE] complete analyze_scene: regions={len(region_evidence)}")

            state.add_trace("hazard_agent_start", {"region_count": len(region_evidence)})
            log("[HAZARD] start identify_hazards")
            hazards = hazard_agent.identify_hazards(region_evidence, attributes)
            state.hazards = hazards
            state.add_trace(
                "hazard_agent_complete", {"hazard_region_count": len(hazards)}
            )
            log(f"[HAZARD] complete identify_hazards: regions={len(hazards)}")

            state.add_trace("report_writer_start", {"region_count": len(region_evidence)})
            log("[REPORT] start write_report")
            draft_report = report_writer_agent.write_report(
                region_evidence, hazards, attributes
            )
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

            state.add_trace("react_loop_start", {"max_iterations": 3})
            log("[REACT] start execute_repair_loop")
            final_report, success, iterations = react_loop.execute_repair_loop(
                draft_report,
                region_evidence,
                hazards,
                attributes,
                trace_cb=state.add_trace,
            )
            state.add_trace(
                "react_loop_complete", {"success": success, "iterations": iterations}
            )
            log(f"[REACT] complete execute_repair_loop: success={success} iterations={iterations}")

            state.draft_report = final_report
            state.validation = {"success": success, "iterations": iterations}

            result_payload = {
                "regionInfo": final_report.get("regions", [])
                if isinstance(final_report, dict)
                else [],
                "representativeImages": state.representative_images,
                "workflowLog": state.trace_log,
            }
            if isinstance(final_report, dict):
                try:
                    store_report(
                        result_payload["regionInfo"],
                        payload.video_path,
                        chat_id=payload.chat_id,
                    )
                    if chat_id:
                        add_chat_message(
                            chat_id,
                            "report",
                            json.dumps(result_payload["regionInfo"], ensure_ascii=False),
                            user_id=user_id,
                            meta={"type": "region_info", "video_path": payload.video_path},
                        )
                    log("[DB] store_report complete")
                except Exception as exc:
                    print(f"[DB] Failed to store report: {exc}", flush=True)

            event_queue.put({"type": "complete", "result": result_payload})
        except Exception as exc:
            log(f"[ERROR] worker failed: {exc}")
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
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
