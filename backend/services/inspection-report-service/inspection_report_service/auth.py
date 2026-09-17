from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .errors import error


@dataclass(frozen=True)
class Principal:
    subject_id: UUID
    account_type: str
    scopes: frozenset[str]
    token: str
    staff_id: UUID | None = None
    role: str | None = None
    customer_status: str | None = None

    def has(self, scope: str) -> bool:
        return scope in self.scopes


bearer = HTTPBearer(auto_error=False)


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
        account_type = actor.get("account_type") or claims.get("account_type")
        if account_type not in {"staff", "customer"}:
            raise ValueError("unsupported actor")
        staff_id = actor.get("staff_id") or claims.get("staff_id")
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise error(401, "invalid_token", "Token is invalid or expired") from exc
    return Principal(
        subject_id=subject,
        account_type=account_type,
        scopes=frozenset(claims.get("scopes", [])),
        token=credentials.credentials,
        staff_id=UUID(staff_id) if staff_id else None,
        role=actor.get("role") or claims.get("role"),
        customer_status=actor.get("customer_status") or claims.get("customer_status"),
    )
