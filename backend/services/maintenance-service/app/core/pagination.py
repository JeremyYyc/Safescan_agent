import base64
import json
from datetime import datetime

from app.core.errors import error


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
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise error(400, "invalid_request", "Invalid pagination cursor") from exc
