from collections.abc import Callable, Iterable

from fastapi import Depends

from safescan_common.http.errors import forbidden

from .principal import Principal


def require_scopes(
    permissions: Iterable[str],
    principal_dependency: Callable,
    *,
    error_code: str = "forbidden",
    error_message: str = "Insufficient permission",
) -> Callable:
    required = frozenset(permissions)

    def dependency(principal: Principal = Depends(principal_dependency)) -> Principal:
        if not principal.has_all(required):
            raise forbidden(error_code, error_message)
        return principal

    return dependency


def require_scope(permission: str, principal_dependency: Callable) -> Callable:
    return require_scopes((permission,), principal_dependency)
