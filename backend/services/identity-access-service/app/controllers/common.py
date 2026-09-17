import secrets
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from safescan_common.http.errors import ApiError
from safescan_common.http.responses import data_response as data

from app.core.config import Settings


def set_auth_cookies(response: Response, settings: Settings, refresh_token: str) -> None:
    csrf = secrets.token_urlsafe(32)
    secure = settings.app_env in {"staging", "production"}
    response.set_cookie(settings.cookie_name, refresh_token, httponly=True, secure=secure,
                        samesite="lax", domain=settings.cookie_domain, path="/api/v1/auth")
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, secure=secure,
                        samesite="lax", domain=settings.cookie_domain, path="/")


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.cookie_name, domain=settings.cookie_domain, path="/api/v1/auth")
    response.delete_cookie(settings.csrf_cookie_name, domain=settings.cookie_domain, path="/")


def token_response(response: Response, settings: Settings, result: dict):
    refresh = result.pop("refresh_token")
    set_auth_cookies(response, settings, refresh)
    return data(result)


def install_identity_error_contract(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def identity_api_error(request: Request, exc: ApiError):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message,
                               "request_id": request_id,
                               "retryable": exc.status_code in {429, 503, 504},
                               "details": exc.details}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def identity_validation_error(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        fields = [{"field": ".".join(map(str, item["loc"])), "reason": item["type"]}
                  for item in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_failed", "message": "Request validation failed",
                               "request_id": request_id, "retryable": False,
                               "details": {"fields": fields}}},
        )
