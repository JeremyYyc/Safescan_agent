import hmac
from typing import Annotated, Callable
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from safescan_common.auth import require_scope
from safescan_common.http.errors import forbidden, unauthorized
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.domain.principal import Principal
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService
from app.services.internal_service import InternalService


bearer = HTTPBearer(auto_error=False)


def auth_service(db: Annotated[Session, Depends(get_db)],
                 settings: Annotated[Settings, Depends(get_settings)]) -> AuthService:
    return AuthService(db, settings)


def profile_service(db: Annotated[Session, Depends(get_db)]) -> ProfileService:
    return ProfileService(db)


def admin_service(db: Annotated[Session, Depends(get_db)],
                  settings: Annotated[Settings, Depends(get_settings)]) -> AdminService:
    return AdminService(db, settings)


def internal_service(db: Annotated[Session, Depends(get_db)],
                     settings: Annotated[Settings, Depends(get_settings)]) -> InternalService:
    return InternalService(db, settings)


def service_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[InternalService, Depends(internal_service)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized("service_token_missing", "Service authentication required")
    return service.authenticate_service(credentials.credentials)


def require_service(permission: str) -> Callable:
    return require_scope(permission, service_principal)


def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return service.authenticate(credentials.credentials)


def optional_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> Principal | None:
    return service.authenticate(credentials.credentials) if credentials else None


def require(permission: str) -> Callable:
    return require_scope(permission, current_principal)


def correlation_id(request: Request, x_request_id: Annotated[str | None, Header()] = None) -> UUID:
    value = x_request_id or request.headers.get("x-correlation-id")
    try:
        return UUID(value) if value else uuid4()
    except ValueError:
        return uuid4()


def validate_csrf(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise forbidden("csrf_invalid", "CSRF token is missing or invalid")
