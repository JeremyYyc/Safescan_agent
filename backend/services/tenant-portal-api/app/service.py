import asyncio
import logging

from fastapi import Request
from redis.exceptions import RedisError

from .auth import Principal
from .cache import cache_key
from .client import Clients, RequestContext
from .errors import ApiError

logger = logging.getLogger("tenant-portal-api.cache")


def request_context(request: Request) -> RequestContext:
    return RequestContext(
        request.state.correlation_id,
        request.headers.get("traceparent"),
        request.headers.get("idempotency-key"),
    )


class PortalService:
    def __init__(self, clients: Clients, cache):
        self.clients = clients
        self.cache = cache

    async def cached(self, namespace, principal, vary, ttl, loader):
        key = cache_key(namespace, principal, vary)
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

    async def invalidate(self, principal):
        if not principal.subject:
            return
        try:
            await self.cache.invalidate_subject(principal.subject)
        except (RedisError, OSError, ValueError) as exc:
            logger.warning(
                "cache invalidation degraded", extra={"error_type": type(exc).__name__}
            )

    async def home(self, principal: Principal, context: RequestContext):
        calls = {
            "applications": self.clients.leasing.request(
                "GET",
                "/internal/v1/applications",
                principal=principal,
                context=context,
                params={"mine": "true", "limit": 5},
            ),
            "leases": self.clients.leasing.request(
                "GET",
                "/internal/v1/leases",
                principal=principal,
                context=context,
                params={"mine": "true", "limit": 5},
            ),
            "maintenance": self.clients.maintenance.request(
                "GET",
                "/internal/v1/maintenance-orders",
                principal=principal,
                context=context,
                params={"mine": "true", "limit": 5},
            ),
            "reports": self.clients.report.request(
                "GET",
                "/internal/v1/reports",
                principal=principal,
                context=context,
                params={"mine": "true", "limit": 5},
            ),
        }
        results = await asyncio.gather(*calls.values(), return_exceptions=True)
        data = {}
        partial = []
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
                data[name] = result
        return data, partial
