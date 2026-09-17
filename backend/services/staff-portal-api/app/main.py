import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .cache import MemoryCache, RedisCache
from .client import Clients
from .config import settings
from .errors import ApiError
from .routes import router
from .service import PortalService

logger = logging.getLogger(settings.service_name)


def error_response(request: Request, error: ApiError) -> JSONResponse:
    cid = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=error.status,
        content={
            "error": {
                "status": error.status,
                "code": error.code,
                "message": error.message,
                "correlation_id": cid,
                "field_errors": error.field_errors,
                "retryable": error.retryable,
                "details": error.details,
            }
        },
        headers={"X-Request-ID": cid},
    )


def create_app(*, clients: Clients | None = None, cache=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.portal = PortalService(
            clients or Clients(),
            cache
            or (
                RedisCache(settings.redis_url) if settings.redis_url else MemoryCache()
            ),
        )
        yield
        if clients is None:
            await app.state.portal.clients.close()

    app = FastAPI(title="SafeScan Staff Portal API", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        cid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = [
            {
                "field": ".".join(str(x) for x in item["loc"] if x != "body"),
                "reason": item["type"],
            }
            for item in exc.errors()
        ]
        return error_response(
            request,
            ApiError(
                422,
                "validation_failed",
                "Request validation failed",
                field_errors=fields,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = (
            "resource_not_found"
            if exc.status_code == 404
            else "method_not_allowed"
            if exc.status_code == 405
            else "invalid_request"
        )
        return error_response(
            request,
            ApiError(
                exc.status_code,
                code,
                "Resource not found"
                if exc.status_code == 404
                else "Method not allowed"
                if exc.status_code == 405
                else "Request failed",
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled portal error",
            extra={"correlation_id": getattr(request.state, "correlation_id", None)},
        )
        return error_response(
            request, ApiError(500, "internal_error", "Internal server error")
        )

    @app.get("/health/live", include_in_schema=False)
    async def live():
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request):
        return {
            "status": "ready",
            "service": settings.service_name,
            "cache": "ready"
            if await request.app.state.portal.cache.ready()
            else "degraded",
        }

    app.include_router(router)
    return app


app = create_app()
