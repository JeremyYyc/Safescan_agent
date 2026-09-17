import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from safescan_common.auth import JWTVerifier

from app.core.config import Settings


password_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(secret_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(secret_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(secret_hash: str) -> bool:
    try:
        return password_hasher.check_needs_rehash(secret_hash)
    except InvalidHashError:
        return True


def new_opaque_token(bytes_length: int = 48) -> str:
    return secrets.token_urlsafe(bytes_length)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def privacy_hash(value: str | None, secret: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(f"{secret}:{value}".encode("utf-8")).hexdigest()


def subject_fingerprint(subject_id: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode("utf-8"), subject_id.encode("utf-8"), hashlib.sha256).digest()


def deletion_peppers(settings: Settings) -> list[tuple[int, str]]:
    current = settings.deletion_pepper.get_secret_value() or (
        settings.jwt_secret.get_secret_value() + ":development-deletion"
    )
    values = [(settings.deletion_pepper_version, current)]
    raw = settings.deletion_previous_peppers.get_secret_value().strip()
    for item in filter(None, (part.strip() for part in raw.split(","))):
        version, pepper = item.split(":", 1)
        values.append((int(version), pepper))
    return values


def create_access_token(
    settings: Settings,
    *,
    subject: str,
    session_id: str | None,
    account_type: str | None,
    auth_version: int | None,
    scopes: list[str],
    audience: str | None = None,
    extra: dict[str, Any] | None = None,
    actor: dict[str, Any] | None = None,
    lifetime_seconds: int | None = None,
) -> tuple[str, int]:
    now = utcnow()
    lifetime = lifetime_seconds or settings.access_token_seconds
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": audience or settings.jwt_audience,
        "sub": subject,
        "sid": session_id,
        "account_type": account_type,
        "av": auth_version,
        "scopes": sorted(set(scopes)),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=lifetime)).timestamp()),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)
    if actor:
        payload["act"] = actor
    encoded = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return encoded, lifetime


def decode_access_token(settings: Settings, token: str, *, audience: str | None = None) -> dict[str, Any]:
    verifier = JWTVerifier(
        secret=settings.jwt_secret.get_secret_value(),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    return verifier.decode(token, audience=audience)
