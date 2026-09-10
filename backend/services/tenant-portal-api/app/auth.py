from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request

from .config import settings
from .errors import ApiError
from .models import CustomerStatus


@dataclass(frozen=True)
class Principal:
    subject: str | None
    status: CustomerStatus | None
    permissions: frozenset[str]
    auth_version: int
    status_version: int
    bearer: str | None
    claims: dict[str, Any]

    @property
    def authenticated(self) -> bool:
        return self.subject is not None


GUEST = Principal(None, None, frozenset({"property:read_market"}), 0, 0, None, {})


def principal_from_request(request: Request, *, optional: bool = False) -> Principal:
    value = request.headers.get("authorization", "")
    if not value:
        if optional:
            return GUEST
        raise ApiError(401, "authentication_required", "Authentication is required")
    if not value.startswith("Bearer "):
        raise ApiError(401, "invalid_token", "Access token is invalid")
    token = value[7:]
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.issuer,
            audience=settings.audience,
        )
        if claims.get("account_type") != "customer":
            raise ApiError(403, "action_forbidden", "Customer access is required")
        status = CustomerStatus(claims.get("customer_status"))
    except ApiError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "token_expired", "Access token has expired") from exc
    except Exception as exc:
        raise ApiError(401, "invalid_token", "Access token is invalid") from exc
    return Principal(
        str(claims["sub"]),
        status,
        frozenset(claims.get("scopes") or []),
        int(claims.get("av", 1)),
        int(claims.get("cv", claims.get("status_version", 1))),
        token,
        claims,
    )


def require_status(principal: Principal, *statuses: CustomerStatus) -> None:
    if not principal.authenticated:
        raise ApiError(401, "authentication_required", "Authentication is required")
    if principal.status not in statuses:
        raise ApiError(
            403, "action_forbidden", "Customer status does not allow this action"
        )


def require_application_eligible(principal: Principal) -> None:
    if principal.status not in (CustomerStatus.PROSPECT, CustomerStatus.FORMER_TENANT):
        raise ApiError(
            403,
            "customer_not_eligible_for_lease",
            "Customer is not eligible to apply",
            details={
                "customer_status": principal.status.value if principal.status else None
            },
        )


def require_permission(principal: Principal, permission: str) -> None:
    if not principal.authenticated:
        raise ApiError(401, "authentication_required", "Authentication is required")
    if permission not in principal.permissions:
        raise ApiError(403, "action_forbidden", "Required permission is missing")
