import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.report import BASE_DIR, OUTPUT_DIR
from app.auth import require_user
from app.db import (
    add_chat_message,
    create_chat,
    delete_pdf_report_and_refs,
    delete_chat,
    get_chat,
    get_chat_messages,
    get_latest_report_id,
    get_report,
    get_report_by_public_id,
    get_latest_report_assets,
    is_db_available,
    list_chats,
    list_chat_report_refs_enriched,
    add_chat_report_ref,
    set_chat_report_ref_status,
    store_pdf_report,
    update_chat_metadata,
    ensure_user_storage_uuid,
    list_reports_by_chat,
    count_reports_referencing_fragment,
    resolve_chat_internal_id,
    resolve_report_internal_id,
    search_reports_by_chat_title,
)

router = APIRouter()


def _resolve_owned_chat(chat_ref: Any, current_user: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    internal_chat_id = resolve_chat_internal_id(chat_ref)
    if internal_chat_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat = get_chat(internal_chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    return internal_chat_id, chat


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


def _resolve_report_title(report: Optional[Dict[str, Any]]) -> str:
    if not report:
        return "Deleted report"
    report_json = report.get("report_json")
    if isinstance(report_json, dict):
        title = report_json.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    source_path = report.get("source_path")
    if isinstance(source_path, str) and source_path.strip():
        try:
            return Path(source_path).name
        except Exception:
            pass
    source_type = report.get("source_type")
    if source_type == "pdf":
        return "Uploaded PDF report"
    return "Report"


def _looks_like_upload_path(raw_value: str) -> bool:
    text = str(raw_value or "").strip()
    if not text:
        return False
    lower = text.lower()
    has_sep = ("/" in text) or ("\\" in text)
    if "uploads" in lower and has_sep:
        return True
    suffix = Path(text).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".mp4", ".mov", ".avi", ".mkv", ".pdf"}:
        if has_sep or ":" in text:
            return True
    return False


def _resolve_path(raw_value: str) -> Optional[Path]:
    text = str(raw_value or "").strip()
    if not _looks_like_upload_path(text):
        return None
    candidate = Path(text)
    try:
        if not candidate.is_absolute():
            return (BASE_DIR / candidate).resolve()
        return candidate.resolve()
    except Exception:
        return None


def _collect_paths_from_payload(payload: Any) -> set[Path]:
    paths: set[Path] = set()
    if isinstance(payload, str):
        resolved = _resolve_path(payload)
        if resolved:
            paths.add(resolved)
        return paths
    if isinstance(payload, list):
        for item in payload:
            paths.update(_collect_paths_from_payload(item))
        return paths
    if isinstance(payload, dict):
        for value in payload.values():
            paths.update(_collect_paths_from_payload(value))
        return paths
    return paths


def _collect_report_asset_paths(report: Dict[str, Any]) -> set[Path]:
    paths: set[Path] = set()
    source_path = report.get("source_path")
    if isinstance(source_path, str):
        resolved = _resolve_path(source_path)
        if resolved:
            paths.add(resolved)
    video_path = report.get("video_path")
    if isinstance(video_path, str):
        resolved = _resolve_path(video_path)
        if resolved:
            paths.add(resolved)
    paths.update(_collect_paths_from_payload(report.get("representative_images")))
    paths.update(_collect_paths_from_payload(report.get("region_info")))
    paths.update(_collect_paths_from_payload(report.get("report_json")))
    return paths


def _cleanup_empty_dirs(start_dirs: set[Path], stop_root: Path) -> None:
    for directory in sorted(start_dirs, key=lambda item: len(str(item)), reverse=True):
        current = directory
        while True:
            if current == stop_root:
                break
            if not current.exists() or not current.is_dir():
                break
            try:
                next(current.iterdir())
                break
            except StopIteration:
                try:
                    current.rmdir()
                except Exception:
                    break
                current = current.parent
            except Exception:
                break


def _cleanup_report_assets(
    reports: list[Dict[str, Any]],
    current_user: Dict[str, Any],
) -> Dict[str, int]:
    user_storage_root = _get_user_storage_root(current_user).resolve()
    deleted_files = 0
    deleted_run_dirs = 0
    skipped_referenced = 0
    skipped_outside = 0
    failed = 0

    file_candidates: set[Path] = set()
    run_dir_candidates: set[Path] = set()
    parent_dir_candidates: set[Path] = set()

    for report in reports:
        for path in _collect_report_asset_paths(report):
            try:
                resolved = path.resolve()
            except Exception:
                continue
            if user_storage_root not in resolved.parents:
                skipped_outside += 1
                continue
            file_candidates.add(resolved)
            parent_dir_candidates.add(resolved.parent)
            for parent in resolved.parents:
                if parent == user_storage_root:
                    break
                if parent.name.startswith("run_"):
                    run_dir_candidates.add(parent)
                    break

    for path in sorted(file_candidates, key=lambda item: len(str(item)), reverse=True):
        if not path.exists() or not path.is_file():
            continue
        if count_reports_referencing_fragment(str(path)) > 0:
            skipped_referenced += 1
            continue
        try:
            path.unlink(missing_ok=True)
            deleted_files += 1
        except Exception:
            failed += 1

    for run_dir in sorted(run_dir_candidates, key=lambda item: len(str(item)), reverse=True):
        if not run_dir.exists() or not run_dir.is_dir():
            continue
        if count_reports_referencing_fragment(str(run_dir)) > 0:
            skipped_referenced += 1
            continue
        try:
            shutil.rmtree(run_dir)
            deleted_run_dirs += 1
        except Exception:
            failed += 1

    _cleanup_empty_dirs(parent_dir_candidates, user_storage_root)

    return {
        "deleted_files": deleted_files,
        "deleted_run_dirs": deleted_run_dirs,
        "skipped_referenced": skipped_referenced,
        "skipped_outside": skipped_outside,
        "cleanup_failed": failed,
    }


@router.post("/reports/upload-pdf")
async def upload_pdf_report_endpoint(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    filename = file.filename.strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Invalid PDF content type")

    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_storage_root = _get_user_storage_root(current_user)
    user_dir = user_storage_root / "PDF" / "uploaded"
    user_dir.mkdir(parents=True, exist_ok=True)
    target_path = user_dir / f"{uuid4().hex}.pdf"
    try:
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    report_title = Path(filename).stem or "Uploaded PDF report"
    report_pk = store_pdf_report(
        user_id=int(user_id),
        source_path=str(target_path),
        title=report_title,
        extracted_text="",
    )
    if not report_pk:
        try:
            target_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to store uploaded report")

    report = get_report(report_pk)
    if not report:
        raise HTTPException(status_code=500, detail="Uploaded report not found")
    return JSONResponse(
        jsonable_encoder(
            {
                "report": {
                    "report_id": report.get("report_id"),
                    "title": _resolve_report_title(report),
                    "source_type": report.get("source_type") or "pdf",
                    "created_at": report.get("created_at"),
                }
            }
        )
    )


@router.post("/chats")
def create_chat_endpoint(
    payload: Optional[Dict[str, Any]] = None, current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    title = None
    chat_type = "report"
    if isinstance(payload, dict):
        title = payload.get("title")
        if isinstance(payload.get("chat_type"), str):
            chat_type = payload.get("chat_type")
    if chat_type not in ("report", "bot"):
        raise HTTPException(status_code=400, detail="chat_type must be report or bot")
    chat_id = create_chat(title=title, user_id=current_user.get("user_id"), chat_type=chat_type)
    if not chat_id:
        raise HTTPException(status_code=500, detail="Failed to create chat")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    return JSONResponse(jsonable_encoder({"chat": chat}))


@router.get("/chats")
def list_chats_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chats = list_chats(user_id=current_user.get("user_id"), limit=limit, offset=offset)
    return JSONResponse(jsonable_encoder({"chats": chats}))


@router.get("/reports/search")
def search_reports_endpoint(
    q: str = Query("", max_length=120),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    keyword = str(q or "").strip()
    items = search_reports_by_chat_title(
        user_id=int(user_id),
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(jsonable_encoder({"keyword": keyword, "items": items}))


@router.get("/chats/{chat_id}/messages")
def get_chat_messages_endpoint(
    chat_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, chat = _resolve_owned_chat(chat_id, current_user)
    messages = get_chat_messages(internal_chat_id, limit=limit, offset=offset) or []
    assets = get_latest_report_assets(internal_chat_id)
    if assets:
        latest_report = None
        for message in reversed(messages):
            if message.get("role") == "report":
                latest_report = message
                break
        if latest_report is not None:
            meta = latest_report.get("meta")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            if assets.get("video_path") and not meta.get("video_path"):
                meta["video_path"] = assets["video_path"]
            if assets.get("representative_images") and not meta.get("representative_images"):
                meta["representative_images"] = assets["representative_images"]
            if assets.get("report_json") and not meta.get("report"):
                meta["report"] = assets["report_json"]
            latest_report["meta"] = meta
    return JSONResponse(jsonable_encoder({"chat": chat, "messages": messages}))


@router.put("/chats/{chat_id}")
def update_chat_endpoint(
    chat_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, _ = _resolve_owned_chat(chat_id, current_user)

    title = payload.get("title") if isinstance(payload, dict) else None
    pinned = payload.get("pinned") if isinstance(payload, dict) else None

    if title is None and pinned is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    if title is not None:
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(status_code=400, detail="title must be a non-empty string")
        title = title.strip()[:255]

    if pinned is not None:
        pinned = bool(pinned)

    updated = update_chat_metadata(internal_chat_id, title=title, pinned=pinned)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update chat")
    return JSONResponse(jsonable_encoder({"chat": updated}))


@router.delete("/chats/{chat_id}")
def delete_chat_endpoint(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, _ = _resolve_owned_chat(chat_id, current_user)
    reports = list_reports_by_chat(internal_chat_id)
    if not delete_chat(internal_chat_id):
        raise HTTPException(status_code=500, detail="Failed to delete chat")
    cleanup = _cleanup_report_assets(reports, current_user)
    return JSONResponse(jsonable_encoder({"deleted": True, "cleanup": cleanup}))


@router.post("/chats/{chat_id}/messages")
def create_message_endpoint(
    chat_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, _ = _resolve_owned_chat(chat_id, current_user)
    role = payload.get("role")
    content = payload.get("content")
    if not isinstance(role, str) or not role:
        raise HTTPException(status_code=400, detail="role is required")
    if role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be user or assistant")
    if not isinstance(content, str) or not content:
        raise HTTPException(status_code=400, detail="content is required")
    message_id = add_chat_message(
        internal_chat_id,
        role,
        content,
        user_id=current_user.get("user_id"),
        meta=payload.get("meta"),
    )
    if not message_id:
        raise HTTPException(status_code=500, detail="Failed to create message")
    return JSONResponse({"message_id": message_id})


@router.get("/chats/{chat_id}/report-refs")
def list_chat_report_refs_endpoint(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, chat = _resolve_owned_chat(chat_id, current_user)
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")

    refs = list_chat_report_refs_enriched(internal_chat_id)
    enriched = []
    for ref in refs:
        status = ref.get("status")
        # "removed" means user manually detached this report from chatbot history.
        if status == "removed":
            continue
        report = ref.get("report")
        report_exists = bool(report)
        # Backward compatibility: old data may use "deleted" for manual detach.
        # If report still exists, treat it as detached and hide it.
        if status == "deleted" and report_exists:
            continue
        # If linked report is missing, always surface as deleted placeholder.
        if not report_exists:
            status = "deleted"

        source_chat_public_id = ref.get("source_chat_id")
        source_title = ref.get("source_chat_title") or _resolve_report_title(report)
        public_report_id = report.get("report_id") if report else f"deleted-{ref.get('id')}"
        enriched.append(
            {
                "report_id": public_report_id,
                "source_chat_id": source_chat_public_id,
                "source_title": source_title,
                "source_type": report.get("source_type") if report else None,
                "status": status,
                "created_at": ref.get("created_at"),
            }
        )
    return JSONResponse(jsonable_encoder({"refs": enriched}))


@router.post("/chats/{chat_id}/report-refs")
def add_chat_report_ref_endpoint(
    chat_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, chat = _resolve_owned_chat(chat_id, current_user)
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")

    report_ref = payload.get("report_id")
    source_chat_ref = payload.get("source_chat_id")
    if report_ref is None and source_chat_ref is None:
        raise HTTPException(status_code=400, detail="report_id or source_chat_id is required")

    report = None
    report_id = None
    source_chat_id = None
    if report_ref is not None:
        report = get_report_by_public_id(report_ref)
        if report:
            report_id = report.get("id")
    else:
        source_chat_id = resolve_chat_internal_id(source_chat_ref)
        if source_chat_id is None:
            raise HTTPException(status_code=404, detail="Source chat not found")
        source_chat = get_chat(source_chat_id)
        if not source_chat or source_chat.get("user_id") != current_user.get("user_id"):
            raise HTTPException(status_code=404, detail="Source chat not found")
        report_id = get_latest_report_id(source_chat_id)
        if not report_id:
            raise HTTPException(status_code=404, detail="No report found for source chat")
        report = get_report(report_id)

    if not report or report.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Report not found")
    if report_id is None:
        report_id = report.get("id")
    if report_id is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if source_chat_id is None:
        source_chat_id = report.get("chat_id")

    add_result = add_chat_report_ref(int(internal_chat_id), int(report_id), source_chat_id=source_chat_id, status="active")
    if add_result is None:
        raise HTTPException(status_code=500, detail="Failed to add report reference")
    return JSONResponse(jsonable_encoder({"added": True, "report_id": report.get("report_id")}))


@router.delete("/chats/{chat_id}/report-refs/{report_id}")
def delete_chat_report_ref_endpoint(
    chat_id: str,
    report_id: str,
    delete_source: bool = Query(False),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    internal_chat_id, chat = _resolve_owned_chat(chat_id, current_user)
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")
    internal_report_id = resolve_report_internal_id(report_id)
    if internal_report_id is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if delete_source:
        report = get_report(internal_report_id)
        if not report or report.get("user_id") != current_user.get("user_id"):
            raise HTTPException(status_code=404, detail="Report not found")
        if report.get("source_type") != "pdf":
            raise HTTPException(status_code=400, detail="Only uploaded PDF report can delete source")
        if not delete_pdf_report_and_refs(internal_report_id, int(current_user.get("user_id"))):
            raise HTTPException(status_code=404, detail="Report not found")
        cleanup = _cleanup_report_assets([report], current_user)
        return JSONResponse(
            jsonable_encoder({"removed": True, "source_deleted": True, "cleanup": cleanup})
        )
    if not set_chat_report_ref_status(internal_chat_id, internal_report_id, "removed"):
        raise HTTPException(status_code=404, detail="Report reference not found")
    return JSONResponse(jsonable_encoder({"removed": True, "deleted": True}))
