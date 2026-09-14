from safescan_common.http.errors import ApiError


def error(status: int, code: str, message: str, **details) -> ApiError:
    return ApiError(status, code, message, details=details)


def hidden_not_found() -> ApiError:
    return error(404, "resource_not_found", "Resource was not found")


def dependency_error(code: str, dependency: str) -> ApiError:
    status = 504 if code == "dependency_timeout" else 503 if code == "dependency_unavailable" else 502
    return error(status, code, "Required dependency could not be verified", dependency=dependency)
