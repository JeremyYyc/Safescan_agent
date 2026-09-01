import json
from app import storage
from starlette.concurrency import run_in_threadpool
from app.api.assets import read_upload
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

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


def _cleanup_report_assets(reports, current_user):
    refs=set()
    for report in reports:
        for key in ('video_asset_id','source_path'):
            if report.get(key): refs.add(report[key])
        refs.update(report.get('representative_images') or [])
    removed=failed=0
    for ref in refs:
        try: removed += bool(storage.remove_unreferenced(ref,current_user['user_id']))
        except Exception: failed += 1
    return {'removed_files':removed,'cleanup_failed':failed}


@router.post("/reports/upload-pdf")
async def upload_pdf_report_endpoint(request: Request,current_user:dict=Depends(require_user)):
    if request.headers.get('content-type','').split(';')[0] != 'application/pdf':
        raise HTTPException(400,'Send raw PDF bytes with application/pdf Content-Type')
    from app.workflow.upload_graph import upload_slot
    with upload_slot():
        data=await read_upload(request)
        if not data.startswith(b'%PDF-'): raise HTTPException(400,'Invalid PDF signature')
        title=request.headers.get('x-file-name','Uploaded PDF report')[:255]
        return await run_in_threadpool(_store_uploaded_pdf,data,title,current_user)


def _store_uploaded_pdf(data,title,current_user):
    ref=storage.put(data,'application/pdf',user_id=current_user['user_id'],category='reports',name=title)
    try:
        pk=store_pdf_report(user_id=current_user['user_id'],source_path=ref,title=title,extracted_text='')
        if not pk: raise RuntimeError('Cannot store PDF metadata')
    except BaseException:
        storage.remove_unreferenced(ref,current_user['user_id'])
        raise
    report=get_report(pk)
    return JSONResponse(jsonable_encoder({'report':{'report_id':report['report_id'],'title':title,'source_type':'pdf','created_at':report['created_at']}}))


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
