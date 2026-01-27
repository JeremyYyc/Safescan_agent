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
    get_latest_report_assets,
    is_db_available,
    list_chats,
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
    if isinstance(payload, dict):
        title = payload.get("title")
    chat_id = create_chat(title=title, user_id=current_user.get("user_id"))
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
