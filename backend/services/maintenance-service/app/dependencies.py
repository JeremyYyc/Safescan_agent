from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.clients.dependencies import DependencyClient
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import error
from app.domain.principal import Principal
from app.services.maintenance import MaintenanceService

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def dependency_client() -> DependencyClient:
    return DependencyClient(get_settings())


def maintenance_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MaintenanceService:
    return MaintenanceService(db, dependency_client(), settings)


def _claims(
    credentials: HTTPAuthorizationCredentials | None, settings: Settings
) -> tuple[dict, str]:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise error(401, "authentication_required", "Authentication required")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise error(401, "invalid_token", "Token is invalid or expired") from exc
    return claims, credentials.credentials


def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    claims, token = _claims(credentials, settings)
    actor = claims.get("act") or {}
    account_type = actor.get("account_type") or claims.get("account_type")
    try:
        subject = UUID(actor.get("sub") or claims["sub"])
        staff = actor.get("staff_id") or claims.get("staff_id")
        staff_id = UUID(staff) if staff else None
    except (ValueError, TypeError, KeyError) as exc:
        raise error(401, "invalid_token", "Token has no supported actor") from exc
    if account_type not in {"staff", "customer"}:
        raise error(401, "invalid_token", "Token has no supported actor")
    return Principal(
        subject_id=subject,
        account_type=account_type,
        scopes=frozenset(claims.get("scopes", [])),
        claims=claims,
        staff_id=staff_id,
        customer_status=actor.get("customer_status") or claims.get("customer_status"),
        role=actor.get("role") or claims.get("role"),
        bearer=token,
    )


def privacy_caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    claims, _ = _claims(credentials, settings)
    if claims.get("sub") != "service:identity-access" or not {
        "privacy:subject_deletion_check"
    }.issubset(claims.get("scopes", [])):
        raise error(403, "action_forbidden", "Service is not allowed")
    return claims
