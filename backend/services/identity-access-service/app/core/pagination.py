from functools import lru_cache

from safescan_common.http.errors import bad_request
from safescan_common.http.pagination import CursorCodec, page as common_page

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_cursor_codec() -> CursorCodec:
    return CursorCodec(get_settings().jwt_secret.get_secret_value())


def encode_cursor(internal_id: int) -> str:
    if internal_id <= 0:
        raise ValueError("cursor id must be positive")
    return get_cursor_codec().encode({"id": internal_id})


def decode_cursor(value: str | None) -> int | None:
    if not value:
        return None
    decoded = get_cursor_codec().decode(value)
    if not isinstance(decoded, dict) or not isinstance(decoded.get("id"), int) or decoded["id"] <= 0:
        raise bad_request("cursor_invalid", "Pagination cursor is invalid")
    return decoded["id"]


def page(rows, limit, serializer, *, cursor_from=None):
    return common_page(
        rows,
        limit,
        serializer,
        cursor_from=cursor_from,
        codec=get_cursor_codec(),
    )
