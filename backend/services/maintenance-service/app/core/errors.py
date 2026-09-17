from typing import Any

from safescan_common.http.errors import ApiError


def error(status: int, code: str, message: str, **details: Any) -> ApiError:
    return ApiError(status, code, message, details=details)


def not_found() -> ApiError:
    return error(404, "resource_not_found", "Resource was not found")


def forbidden() -> ApiError:
    return error(403, "action_forbidden", "Action is not allowed")


def version_conflict(current: int) -> ApiError:
    return error(
        409, "version_conflict", "Resource version is stale", current_version=current
    )
