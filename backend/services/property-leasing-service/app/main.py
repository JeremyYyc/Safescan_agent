from uuid import uuid4

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from safescan_common.http.errors import ApiError
from safescan_common.http.health import create_health_router
from safescan_common.http.middleware import install_http_infrastructure

from app.controllers.api import router
from app.core.database import get_engine


app = FastAPI(title="SafeScan Property Leasing Service", version="1.0.0")
install_http_infrastructure(app)


def error_body(code: str, message: str, request_id: str, details: dict | None = None,
               retryable: bool = False) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id,
                      "retryable": retryable, "details": details or {}}}


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    retryable = exc.status_code in {429, 503, 504}
    return JSONResponse(content=error_body(exc.code, exc.message, request_id,
                                           exc.details, retryable),
                        status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    details = {"fields": [{"field": ".".join(map(str, item["loc"])),
                            "reason": item["type"]} for item in exc.errors()]}
    return JSONResponse(content=error_body("validation_failed", "Request validation failed",
                                           request_id, details), status_code=422)


app.include_router(router)


def readiness() -> None:
    with get_engine().connect() as connection:
        connection.execute(sa.text(
            "SELECT 1 FROM property_leasing.customer_lease_slots LIMIT 1"
        ))


app.include_router(create_health_router("property-leasing", readiness))
