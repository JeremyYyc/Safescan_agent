from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request

from .config import settings
from .errors import ApiError
from .models import Role


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    permissions: frozenset[str]
    scopes: tuple[str, ...]
    auth_version: int
    role_version: int
    bearer: str
    claims: dict[str, Any]


def principal_from_request(request: Request) -> Principal:
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer "):
        raise ApiError(401, "authentication_required", "Authentication is required")
    token = value[7:]
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.issuer,
            audience=settings.audience,
        )
        if claims.get("account_type") != "staff":
            raise ApiError(403, "action_forbidden", "Staff access is required")
        role = Role(claims.get("role") or claims.get("role_code"))
    except ApiError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "token_expired", "Access token has expired") from exc
    except Exception as exc:
        raise ApiError(401, "invalid_token", "Access token is invalid") from exc
    return Principal(
        subject=str(claims["sub"]),
        role=role,
        permissions=frozenset(claims.get("permissions") or claims.get("scopes") or []),
        scopes=tuple(sorted(claims.get("resource_scopes") or [])),
        auth_version=int(claims.get("av", 1)),
        role_version=int(claims.get("rv", 1)),
        bearer=token,
        claims=claims,
    )


def require_roles(principal: Principal, *roles: Role) -> None:
    if principal.role not in roles:
        raise ApiError(
            403, "action_forbidden", "This staff role cannot perform the action"
        )


def require_permission(principal: Principal, permission: str) -> None:
    if permission not in principal.permissions:
        raise ApiError(403, "action_forbidden", "Required permission is missing")


def require_report_generation(principal: Principal) -> None:
    require_roles(principal, Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    require_permission(
        principal,
        "report:generate_all"
        if principal.role is Role.MANAGER_ADMIN
        else "report:generate_assigned",
    )
