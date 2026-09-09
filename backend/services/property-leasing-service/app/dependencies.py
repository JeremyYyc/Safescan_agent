from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.clients.identity import IdentityClient
from app.core.config import Settings, get_settings
from app.core.cache import get_query_cache
from app.core.database import get_db
from app.core.errors import error
from app.domain.principal import Principal
from app.services.leasing_service import LeasingService


bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def identity_client() -> IdentityClient:
    return IdentityClient(get_settings())


def leasing_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeasingService:
    return LeasingService(db, identity_client(), settings, get_query_cache())


def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise error(401, "authentication_required", "Authentication required")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"], audience=settings.jwt_audience, issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"]},
        )
        actor = claims.get("act") or {}
        subject = UUID(actor.get("sub") or claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise error(401, "invalid_token", "Token is invalid or expired") from exc
    account_type = actor.get("account_type") or claims.get("account_type")
    if account_type not in {"staff", "customer"}:
        raise error(401, "invalid_token", "Token has no supported actor")
    staff_id = actor.get("staff_id") or claims.get("staff_id")
    return Principal(
        subject_id=subject,
        account_type=account_type,
        scopes=frozenset(claims.get("scopes", [])),
        claims=claims,
        staff_id=UUID(staff_id) if staff_id else None,
        customer_status=actor.get("customer_status") or claims.get("customer_status"),
        role=actor.get("role") or claims.get("role"),
    )


def optional_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal | None:
    return current_principal(credentials, settings) if credentials else None


@lru_cache(maxsize=1)
def identity_client() -> IdentityClient:
    return IdentityClient(get_settings())


def leasing_service(
    db: Annotated[Session, Depends(get_db)],
    identity: Annotated[IdentityClient, Depends(identity_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeasingService:
    return LeasingService(db, identity, settings)
