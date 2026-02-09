import base64
import hashlib
import hmac
import os
from typing import Dict, Optional


PUBLIC_ID_VERSION = 1
KIND_USER = "user"
KIND_CHAT = "chat"
KIND_REPORT = "report"

_KIND_TO_CODE: Dict[str, int] = {
    KIND_USER: 0x11,
    KIND_CHAT: 0x27,
    KIND_REPORT: 0x3D,
}
_CODE_TO_KIND: Dict[int, str] = {value: key for key, value in _KIND_TO_CODE.items()}
_KIND_TO_TAG: Dict[str, str] = {
    KIND_USER: "k2",
    KIND_CHAT: "m8",
    KIND_REPORT: "q5",
}
_TAG_TO_KIND: Dict[str, str] = {value: key for key, value in _KIND_TO_TAG.items()}


def _get_secret_bytes() -> bytes:
    raw = (
        os.getenv("PUBLIC_ID_SECRET")
        or os.getenv("SECRET_KEY")
        or os.getenv("APP_SECRET")
        or "safe_scan_public_id_default_change_me"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _urlsafe_b64_decode(text: str) -> Optional[bytes]:
    value = str(text or "").strip()
    if not value:
        return None
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception:
        return None


def _is_hex_32(text: str) -> bool:
    value = str(text or "").strip().lower()
    if len(value) != 32:
        return False
    try:
        int(value, 16)
        return True
    except Exception:
        return False


def encode_public_id(kind: str, raw_uuid_hex: str) -> str:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in _KIND_TO_CODE:
        raise ValueError("Unsupported public id kind")
    raw_value = str(raw_uuid_hex or "").strip().lower()
    if not _is_hex_32(raw_value):
        raise ValueError("raw_uuid_hex must be 32 hex characters")

    version = PUBLIC_ID_VERSION
    kind_code = _KIND_TO_CODE[normalized_kind]
    raw_uuid = bytes.fromhex(raw_value)
    secret = _get_secret_bytes()

    mask = hmac.new(secret, bytes([version, kind_code]), hashlib.sha256).digest()[:16]
    masked_uuid = _xor_bytes(raw_uuid, mask)
    checksum = hmac.new(
        secret,
        bytes([version, kind_code]) + raw_uuid,
        hashlib.sha256,
    ).digest()[:4]
    payload = bytes([version, kind_code]) + masked_uuid + checksum
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    tag = _KIND_TO_TAG[normalized_kind]
    return f"{tag}_{token}"


def decode_public_id(value: str, expected_kind: Optional[str] = None) -> Optional[Dict[str, str]]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    normalized_expected = str(expected_kind or "").strip().lower() or None
    if normalized_expected and normalized_expected not in _KIND_TO_CODE:
        return None

    if _is_hex_32(raw_value):
        if normalized_expected:
            return {"kind": normalized_expected, "uuid_hex": raw_value.lower()}
        return None

    if "_" not in raw_value:
        return None
    tag, token = raw_value.split("_", 1)
    tag = str(tag or "").strip()
    token = str(token or "").strip()
    if not tag or not token:
        return None

    tag_kind = _TAG_TO_KIND.get(tag)
    if not tag_kind:
        return None
    if normalized_expected and tag_kind != normalized_expected:
        return None

    payload = _urlsafe_b64_decode(token)
    if payload is None or len(payload) != 22:
        return None

    version = payload[0]
    kind_code = payload[1]
    masked_uuid = payload[2:18]
    checksum = payload[18:22]
    decoded_kind = _CODE_TO_KIND.get(kind_code)
    if not decoded_kind:
        return None
    if decoded_kind != tag_kind:
        return None
    if normalized_expected and decoded_kind != normalized_expected:
        return None
    if version != PUBLIC_ID_VERSION:
        return None

    secret = _get_secret_bytes()
    mask = hmac.new(secret, bytes([version, kind_code]), hashlib.sha256).digest()[:16]
    raw_uuid = _xor_bytes(masked_uuid, mask)
    expected_checksum = hmac.new(
        secret,
        bytes([version, kind_code]) + raw_uuid,
        hashlib.sha256,
    ).digest()[:4]
    if not hmac.compare_digest(expected_checksum, checksum):
        return None

    return {"kind": decoded_kind, "uuid_hex": raw_uuid.hex()}
