import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.auth import require_user
from app.db import (
    add_chat_message,
    create_chat,
    delete_chat,
    get_chat,
    get_chat_messages,
    get_latest_report_id,
    get_report,
    get_latest_report_assets,
    is_db_available,
    list_chats,
    list_chat_report_refs,
    add_chat_report_ref,
    set_chat_report_ref_status,
    update_chat_metadata,
)

router = APIRouter()


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


@router.get("/chats/{chat_id}/messages")
def get_chat_messages_endpoint(
    chat_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = get_chat_messages(chat_id, limit=limit, offset=offset) or []
    assets = get_latest_report_assets(chat_id)
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
    chat_id: int,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")

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

    updated = update_chat_metadata(chat_id, title=title, pinned=pinned)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update chat")
    return JSONResponse(jsonable_encoder({"chat": updated}))


@router.delete("/chats/{chat_id}")
def delete_chat_endpoint(
    chat_id: int,
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if not delete_chat(chat_id):
        raise HTTPException(status_code=500, detail="Failed to delete chat")
    return JSONResponse(jsonable_encoder({"deleted": True}))


@router.post("/chats/{chat_id}/messages")
def create_message_endpoint(
    chat_id: int,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    role = payload.get("role")
    content = payload.get("content")
    if not isinstance(role, str) or not role:
        raise HTTPException(status_code=400, detail="role is required")
    if role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be user or assistant")
    if not isinstance(content, str) or not content:
        raise HTTPException(status_code=400, detail="content is required")
    message_id = add_chat_message(
        chat_id,
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
    chat_id: int,
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")

    refs = list_chat_report_refs(chat_id)
    enriched = []
    for ref in refs:
        source_chat_id = ref.get("source_chat_id")
        source_chat = get_chat(source_chat_id) if source_chat_id else None
        source_title = source_chat.get("title") if source_chat else None
        enriched.append(
            {
                "report_id": ref.get("report_id"),
                "source_chat_id": source_chat_id,
                "source_title": source_title,
                "status": ref.get("status"),
                "created_at": ref.get("created_at"),
            }
        )
    return JSONResponse(jsonable_encoder({"refs": enriched}))


@router.post("/chats/{chat_id}/report-refs")
def add_chat_report_ref_endpoint(
    chat_id: int,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")

    report_id = payload.get("report_id")
    source_chat_id = payload.get("source_chat_id")
    if report_id is None and source_chat_id is None:
        raise HTTPException(status_code=400, detail="report_id or source_chat_id is required")

    report = None
    if report_id is not None:
        try:
            report_id = int(report_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid report_id")
        report = get_report(report_id)
    else:
        try:
            source_chat_id = int(source_chat_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid source_chat_id")
        source_chat = get_chat(source_chat_id)
        if not source_chat or source_chat.get("user_id") != current_user.get("user_id"):
            raise HTTPException(status_code=404, detail="Source chat not found")
        report_id = get_latest_report_id(source_chat_id)
        if not report_id:
            raise HTTPException(status_code=404, detail="No report found for source chat")
        report = get_report(report_id)

    if not report or report.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Report not found")
    if source_chat_id is None:
        source_chat_id = report.get("chat_id")

    if not add_chat_report_ref(chat_id, report_id, source_chat_id=source_chat_id, status="active"):
        raise HTTPException(status_code=500, detail="Failed to add report reference")
    return JSONResponse(jsonable_encoder({"added": True, "report_id": report_id}))


@router.delete("/chats/{chat_id}/report-refs/{report_id}")
def delete_chat_report_ref_endpoint(
    chat_id: int,
    report_id: int,
    current_user: Dict[str, Any] = Depends(require_user),
) -> JSONResponse:
    if not is_db_available():
        raise HTTPException(status_code=500, detail="Database is not configured")
    chat = get_chat(chat_id)
    if not chat or chat.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.get("chat_type") != "bot":
        raise HTTPException(status_code=400, detail="Chat is not a chatbot session")
    if not set_chat_report_ref_status(chat_id, report_id, "deleted"):
        raise HTTPException(status_code=404, detail="Report reference not found")
    return JSONResponse(jsonable_encoder({"deleted": True}))
