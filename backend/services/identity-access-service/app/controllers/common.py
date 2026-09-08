import secrets

from fastapi import Response
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
