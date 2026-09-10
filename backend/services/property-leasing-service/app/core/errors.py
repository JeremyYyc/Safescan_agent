from typing import Any

from safescan_common.http.errors import ApiError


def error(status: int, code: str, message: str, **details: Any) -> ApiError:
    return ApiError(status, code, message, details=details)


def resource_not_found(code: str = "resource_not_found") -> ApiError:
    return error(404, code, "Resource was not found")


def action_forbidden(message: str = "Action is not allowed", **details: Any) -> ApiError:
    return error(403, "action_forbidden", message, **details)


def state_conflict(code: str, current: str, allowed: list[str]) -> ApiError:
    return error(409, code, "Resource state does not allow this action",
                 current_state=current, allowed_states=allowed)


def version_conflict(current: int) -> ApiError:
    return error(409, "version_conflict", "Resource version is stale", current_version=current)
