"""HTTP contracts and FastAPI integration."""

from .errors import ApiError, bad_request, conflict, forbidden, not_found, unauthorized
from .middleware import install_http_infrastructure
from .pagination import CursorCodec, decode_cursor, encode_cursor, page
from .responses import data_response, error_body

__all__ = [
    "ApiError",
    "CursorCodec",
    "bad_request",
    "conflict",
    "data_response",
    "decode_cursor",
    "encode_cursor",
    "error_body",
    "forbidden",
    "install_http_infrastructure",
    "not_found",
    "page",
    "unauthorized",
]
