import base64
import hashlib
import hmac
import json
from app.settings import get_settings
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException

from app.db import create_auth_session, get_user_by_id, validate_auth_session


def _get_secret() -> str:
    return get_settings().require_secret("AUTH_SECRET")


def _get_expiry_seconds() -> int:
    return get_settings().AUTH_EXPIRE_HOURS * 60 * 60


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(data: str) -> str:
    secret = _get_secret().encode("utf-8")
    return hmac.new(secret, data.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(user: Dict[str, Any], session_id: Optional[str] = None) -> str:
    now = int(time.time())
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_get_expiry_seconds())
    session_id = session_id or create_auth_session(int(user["user_id"]), expires_at)
    if not session_id:
        raise RuntimeError("Unable to create authentication session")
    payload = {
        "sub": str(user.get("public_id") or user.get("storage_uuid") or ""),
        "sid": session_id,
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "username": user.get("username"),
        "account_type": user.get("account_type"),
        "role": user.get("role"),
        "customer_status": user.get("customer_status"),
        "auth_version": int(user.get("auth_version") or 1),
        "iss": settings.AUTH_ISSUER,
        "aud": settings.AUTH_AUDIENCE,
        "jti": uuid4().hex,
        "iat": now,
        "nbf": now,
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
    settings = get_settings()
    if payload.get("iss") != settings.AUTH_ISSUER or payload.get("aud") != settings.AUTH_AUDIENCE:
        return None
    nbf = payload.get("nbf")
    if not isinstance(nbf, (int, float)) or nbf > time.time() + 30:
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
    session_id = payload.get("sid")
    if not session_id or not validate_auth_session(
        str(session_id), int(user["user_id"]), int(payload.get("auth_version") or 0)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user
