import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

from fastapi import Request
from redis.exceptions import RedisError

from .auth import Principal
from .cache import Cache, private_cache_key
from .client import Clients, RequestContext
from .errors import ApiError
from .models import Role

logger = logging.getLogger("staff-portal-api.cache")


def context_from_request(request: Request) -> RequestContext:
    return RequestContext(
        correlation_id=request.state.correlation_id,
        traceparent=request.headers.get("traceparent"),
        idempotency_key=request.headers.get("idempotency-key"),
    )


class PortalService:
    def __init__(self, clients: Clients, cache: Cache):
        self.clients = clients
        self.cache = cache

    async def cached(
        self,
        namespace: str,
        principal: Principal,
        vary: str,
        ttl: int,
        loader: Awaitable[Any],
    ) -> Any:
        key = private_cache_key(namespace, principal, vary)
        try:
            hit = await self.cache.get(key)
            if hit is not None:
                return hit
        except (RedisError, OSError, ValueError) as exc:
            logger.warning(
                "cache read degraded", extra={"error_type": type(exc).__name__}
            )
        value = await loader
        try:
            await self.cache.set(key, value, ttl)
        except (RedisError, OSError, ValueError) as exc:
            logger.warning(
                "cache write degraded", extra={"error_type": type(exc).__name__}
            )
        return value

    async def invalidate_after_write(self, principal: Principal) -> None:
        try:
            await self.cache.invalidate_subject(principal.subject)
        except (RedisError, OSError, ValueError) as exc:
            logger.warning(
                "cache invalidation degraded", extra={"error_type": type(exc).__name__}
            )

    async def dashboard(
        self, principal: Principal, context: RequestContext
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        calls = {
            "assigned_properties": self.clients.leasing.request(
                "GET",
                "/internal/v1/properties",
                principal=principal,
                context=context,
                params={"scope": "assigned", "limit": 1},
            )
        }
        if principal.role in (Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN):
            calls["open_prospects"] = self.clients.leasing.request(
                "GET",
                "/internal/v1/prospect-cases",
                principal=principal,
                context=context,
                params={"status": "open", "limit": 1},
            )
        if principal.role in (
            Role.PROPERTY_MANAGER,
            Role.MAINTAINER,
            Role.MANAGER_ADMIN,
        ):
            calls["open_maintenance"] = self.clients.maintenance.request(
                "GET",
                "/internal/v1/maintenance-orders",
                principal=principal,
                context=context,
                params={"status": "open", "limit": 1},
            )
        if principal.role in (Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN):
            calls["running_report_jobs"] = self.clients.report.request(
                "GET",
                "/internal/v1/reports",
                principal=principal,
                context=context,
                params={"status": "running", "limit": 1},
            )
        results = await asyncio.gather(*calls.values(), return_exceptions=True)
        cards: dict[str, Any] = {}
        partial: list[dict[str, Any]] = []
        for name, result in zip(calls, results):
            if isinstance(result, Exception):
                error = (
                    result
                    if isinstance(result, ApiError)
                    else ApiError(
                        503,
                        "dependency_unavailable",
                        "Dependency unavailable",
                        retryable=True,
                    )
                )
                partial.append(
                    {
                        "component": name,
                        "code": error.code,
                        "retryable": error.retryable,
                        "details": error.details,
                    }
                )
            else:
                items = result.get("items", result if isinstance(result, list) else [])
                cards[name] = {
                    "count": result.get("total", len(items))
                    if isinstance(result, dict)
                    else len(items)
                }
        return {
            "staff": {"id": principal.subject, "role": principal.role.value},
            "cards": cards,
        }, partial
