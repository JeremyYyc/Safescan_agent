from typing import Any


class ApiError(Exception):
    """Operational API error rendered through the shared error contract."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def bad_request(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(400, code, message, details=details)


def unauthorized(code: str = "unauthorized", message: str = "Authentication required") -> ApiError:
    return ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(code: str = "forbidden", message: str = "Insufficient permission") -> ApiError:
    return ApiError(403, code, message)


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def conflict(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(409, code, message, details=details)
