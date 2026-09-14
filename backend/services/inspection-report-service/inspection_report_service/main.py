from contextlib import asynccontextmanager
from uuid import uuid4

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from safescan_common.http.errors import ApiError
from safescan_common.http.health import create_health_router
from safescan_common.http.middleware import install_http_infrastructure

from .database import get_engine
from .routes import leasing_client, router
from .storage import minio_client
from .config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.formal_runtime:
        leasing_client().require_identity_service_token()
    yield


app = FastAPI(
    title="SafeScan Inspection Report Service",
    version="1.0.0",
    lifespan=lifespan,
)
install_http_infrastructure(app)


def error_body(code: str, message: str, request_id: str, details=None, retryable=False):
    return {"error": {"code": code, "message": message, "request_id": request_id,
                      "retryable": retryable, "details": details or {}}}


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    rid = getattr(request.state, "request_id", str(uuid4()))
    retryable = exc.status_code in {429, 503, 504}
    return JSONResponse(error_body(exc.code, exc.message, rid, exc.details, retryable),
                        status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    rid = getattr(request.state, "request_id", str(uuid4()))
    fields = [{"field": ".".join(map(str, item["loc"])), "reason": item["type"]}
              for item in exc.errors()]
    return JSONResponse(error_body("validation_failed", "Request validation failed", rid,
                                   {"fields": fields}), status_code=422)


app.include_router(router)


def readiness() -> None:
    with get_engine().connect() as connection:
        connection.execute(sa.text("SELECT 1 FROM inspection_report.report_jobs LIMIT 1"))
    settings = get_settings()
    if settings.formal_runtime:
        leasing_client().require_identity_service_token()
    client = minio_client(
        settings.minio_endpoint, settings.minio_access_key.get_secret_value(),
        settings.minio_secret_key.get_secret_value(), settings.minio_secure,
    )
    for bucket in (settings.minio_media_bucket, settings.minio_derived_bucket):
        if not client.bucket_exists(bucket):
            raise RuntimeError(f"Required private bucket is unavailable: {bucket}")


app.include_router(create_health_router("inspection-report", readiness))
