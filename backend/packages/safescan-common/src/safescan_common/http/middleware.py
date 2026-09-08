from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import ApiError
from .responses import error_body


def resolve_request_id(value: str | None) -> str:
    try:
        return str(UUID(value)) if value else str(uuid4())
    except (TypeError, ValueError):
        return str(uuid4())


def install_http_infrastructure(app: FastAPI, *, cache_control: str = "no-store") -> None:
    """Install SafeScan request context and standard operational error handlers."""

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
        request_id = resolve_request_id(supplied)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if cache_control:
            response.headers["Cache-Control"] = cache_control
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, request_id, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        details = {
            "fields": [
                {"path": ".".join(map(str, item["loc"])), "message": item["msg"]}
                for item in exc.errors()
            ]
        }
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error", "Request validation failed", request_id, details
            ),
        )
