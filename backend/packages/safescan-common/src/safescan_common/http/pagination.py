import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from .errors import bad_request


RowT = TypeVar("RowT")
OutputT = TypeVar("OutputT")


class CursorCodec:
    """URL-safe cursor codec with optional HMAC tamper protection."""

    def __init__(self, secret: str | bytes | None = None) -> None:
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else secret

    def encode(self, value: Any) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        if not self._secret:
            return payload
        signature = hmac.new(self._secret, payload.encode("ascii"), hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{payload}.{encoded_signature}"

    def decode(self, value: str) -> Any:
        try:
            payload = value
            if self._secret:
                payload, supplied_signature = value.split(".", maxsplit=1)
                expected = hmac.new(
                    self._secret, payload.encode("ascii"), hashlib.sha256
                ).digest()
                padded_signature = supplied_signature + "=" * (-len(supplied_signature) % 4)
                actual = base64.urlsafe_b64decode(padded_signature)
                if not hmac.compare_digest(actual, expected):
                    raise ValueError("cursor signature mismatch")
            padded = payload + "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
            raise bad_request("cursor_invalid", "Pagination cursor is invalid") from exc


default_cursor_codec = CursorCodec()


def encode_cursor(internal_id: int) -> str:
    if internal_id <= 0:
        raise ValueError("cursor id must be positive")
    return default_cursor_codec.encode({"id": internal_id})


def decode_cursor(value: str | None) -> int | None:
    if not value:
        return None
    decoded = default_cursor_codec.decode(value)
    if not isinstance(decoded, dict) or not isinstance(decoded.get("id"), int) or decoded["id"] <= 0:
        raise bad_request("cursor_invalid", "Pagination cursor is invalid")
    return decoded["id"]


def page(
    rows: Sequence[RowT],
    limit: int,
    serializer: Callable[[RowT], OutputT],
    *,
    cursor_from: Callable[[RowT], int] | None = None,
    codec: CursorCodec = default_cursor_codec,
) -> dict[str, Any]:
    has_more = len(rows) > limit
    visible = rows[:limit]

    def default_cursor(row: RowT) -> int:
        if not isinstance(row, Mapping):
            raise TypeError("cursor_from is required for non-mapping rows")
        return int(row["id"])

    cursor_factory = cursor_from or default_cursor
    next_cursor = (
        codec.encode({"id": cursor_factory(visible[-1])}) if has_more and visible else None
    )
    return {
        "data": [serializer(row) for row in visible],
        "meta": {"next_cursor": next_cursor},
    }
