import base64
import json
from datetime import datetime

from safescan_common.http.errors import bad_request


def encode_cursor(created_at: datetime, row_id: int) -> str:
    raw = json.dumps([created_at.isoformat(), row_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[datetime, int] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        timestamp, row_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(timestamp), int(row_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise bad_request("invalid_request", "Invalid pagination cursor")
