import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException

from app.db import get_user_by_id


def _get_secret() -> str:
    return os.getenv("AUTH_SECRET", "dev-secret")


def _get_expiry_seconds() -> int:
    raw = os.getenv("AUTH_EXPIRE_HOURS", "8").strip()
    try:
        hours = int(raw)
    except ValueError:
        hours = 8
    if hours <= 0:
        hours = 8
    return hours * 60 * 60


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(data: str) -> str:
    secret = _get_secret().encode("utf-8")
    return hmac.new(secret, data.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(user: Dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "username": user.get("username"),
        "iat": now,
        "exp": now + _get_expiry_seconds(),
    }
    encoded = _b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    signature = _sign(encoded)
    return f"{encoded}.{signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 2:
        return None
    encoded, signature = parts
    expected = _sign(encoded)
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_b64decode(encoded))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    if exp < time.time():
        return None
    return payload


def require_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token)
    if not payload or not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = get_user_by_id(int(payload["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user
