from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        field_errors: list[dict[str, str]] | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.field_errors = field_errors or []


PRIVATE_404_CODES = {
    "property_not_visible",
    "prospect_case_not_found",
    "case_access_denied",
    "lease_access_required",
    "order_not_found",
    "property_access_denied",
    "inspection_not_found",
    "job_not_found",
    "report_not_found",
    "report_access_denied",
    "report_history_access_required",
}


def map_downstream_error(status: int, payload: Any, dependency: str) -> ApiError:
    try:
        body = payload["error"]
        code = str(body["code"])
        message = str(body.get("message") or "Request failed")
        retryable = bool(body.get("retryable", False))
        details = body.get("details") if isinstance(body.get("details"), dict) else {}
        fields = (
            body.get("field_errors", details.get("fields", []))
            if code == "validation_failed"
            else []
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            502,
            "dependency_invalid_response",
            "A dependency returned an invalid response",
            details={"dependency": dependency},
        ) from exc
    if status == 404 or code in PRIVATE_404_CODES:
        return ApiError(404, "resource_not_found", "Resource not found")
    allowed = {401, 403, 409, 422, 429}
    if status in allowed:
        return ApiError(
            status,
            code,
            message,
            retryable=retryable,
            details=details,
            field_errors=fields,
        )
    if status >= 500:
        return ApiError(
            503,
            "dependency_unavailable",
            "A required service is unavailable",
            retryable=True,
            details={"dependency": dependency},
        )
    return ApiError(
        502,
        "dependency_invalid_response",
        "A dependency returned an invalid response",
        details={"dependency": dependency},
    )
