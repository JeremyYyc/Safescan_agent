import asyncio
import json
import os
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
from app.db import get_chat, update_chat_title
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
            from app.agents.comfort_agent import ComfortAgent
            from app.agents.compliance_agent import ComplianceAgent
            from app.agents.scoring_agent import ScoringAgent
            from app.agents.recommendation_agent import RecommendationAgent
            from app.agents.report_writer_agent import ReportWriterAgent
            from app.agents.title_agent import TitleAgent
            from app.agents.validator_agent import ValidatorAgent
            from app.db import add_chat_report_detail, store_report
            from app.workflow.orchestrator import WorkflowOrchestrator
            from app.workflow.react_loop import ReactRepairLoop
            from app.llm_registry import get_max_concurrency

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

            scene_agent = SceneUnderstandingAgent()
            hazard_agent = SafetyHazardAgent()
            comfort_agent = ComfortAgent()
            compliance_agent = ComplianceAgent()
            scoring_agent = ScoringAgent()
            recommendation_agent = RecommendationAgent()
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
                state.representative_images,
                attributes,
                yolo_summaries=state.yolo_summaries,
            )
            state.region_evidence = region_evidence
            state.add_trace(
                "scene_agent_complete", {"region_count": len(region_evidence)}
            )
            log(f"[SCENE] complete analyze_scene: regions={len(region_evidence)}")
            log("------------------------------------------------------------------------------------")

            state.add_trace("hazard_agent_start", {"region_count": len(region_evidence)})
            log("[HAZARD] start identify_hazards")
            max_concurrency = get_max_concurrency()
            hazard_concurrency = max(1, max_concurrency - 1)
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                hazard_future = executor.submit(
                    hazard_agent.identify_hazards,
                    region_evidence,
                    attributes,
                    hazard_concurrency,
                )
                comfort_future = executor.submit(
                    comfort_agent.analyze_comfort,
                    region_evidence,
                    attributes,
                )
                hazards = hazard_future.result()
                comfort_result = comfort_future.result()
            state.hazards = hazards
            state.add_trace(
                "hazard_agent_complete", {"hazard_region_count": len(hazards)}
            )
            log(f"[HAZARD] complete identify_hazards: regions={len(hazards)}")
            log("------------------------------------------------------------------------------------")

            state.add_trace("comfort_agent_complete", {"has_observations": bool(comfort_result)})
            log("[COMFORT] complete analyze_comfort")
            log("------------------------------------------------------------------------------------")

            state.add_trace("compliance_agent_start", {})
            log("[COMPLIANCE] start build_compliance")
            with ThreadPoolExecutor(max_workers=2) as executor:
                compliance_future = executor.submit(
                    compliance_agent.build_compliance,
                    hazards,
                )
                scoring_future = executor.submit(
                    scoring_agent.score_home,
                    hazards,
                    comfort_result,
                    attributes,
                )
                compliance_result = compliance_future.result()
                scoring_result = scoring_future.result()
            state.add_trace("compliance_agent_complete", {})
            log("[COMPLIANCE] complete build_compliance")
            log("------------------------------------------------------------------------------------")

            state.add_trace("scoring_agent_complete", {})
            log("[SCORING] complete score_home")
            log("------------------------------------------------------------------------------------")

            state.add_trace("recommendation_agent_start", {})
            log("[RECOMMENDATION] start build_recommendations")
            recommendations_result = recommendation_agent.build_recommendations(
                hazards,
                scoring_result,
                comfort_result,
                attributes,
            )
            state.add_trace("recommendation_agent_complete", {})
            log("[RECOMMENDATION] complete build_recommendations")
            log("------------------------------------------------------------------------------------")

            state.add_trace("report_writer_start", {"region_count": len(region_evidence)})
            log("[REPORT] start write_report")
            draft_report = report_writer_agent.write_report(
                region_evidence,
                hazards,
                attributes,
                scoring_result,
                comfort_result,
                compliance_result,
                recommendations_result,
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

            result_payload = {
                "regionInfo": final_report.get("regions", [])
                if isinstance(final_report, dict)
                else [],
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
