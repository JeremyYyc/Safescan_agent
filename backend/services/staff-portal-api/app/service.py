import asyncio
import logging
from collections.abc import Awaitable, Callable
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
        loader: Callable[[], Awaitable[Any]],
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
        value = await loader()
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

    async def enrich_maintenance(
        self, principal: Principal, context: RequestContext, page: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Expand only the authorized page with two bounded batch projections.

        Context is optional: a directory/storage outage must not hide valid work
        orders. Never mutate the cached Maintenance response in place.
        """
        items = page.get("items", [])
        property_ids = sorted(
            {
                str(item["property"]["id"])
                for item in items
                if isinstance(item.get("property"), dict) and item["property"].get("id")
            }
        )
        staff_ids = sorted(
            {
                str(item["assigned_staff"]["id"])
                for item in items
                if isinstance(item.get("assigned_staff"), dict)
                and item["assigned_staff"].get("id")
            }
        )
        calls = {}
        if property_ids:
            calls["maintenance_properties"] = self.clients.leasing.request(
                "POST",
                "/internal/v1/projections/properties:batch",
                principal=principal,
                context=context,
                json={"ids": property_ids},
            )
        if staff_ids:
            calls["maintenance_assignees"] = self.clients.identity.request(
                "POST",
                "/api/v1/iam/staff/display-names:batch",
                principal=principal,
                context=context,
                json={"ids": staff_ids},
            )
        results = await asyncio.gather(*calls.values(), return_exceptions=True)
        projections = {}
        partial = []
        for name, result in zip(calls, results):
            if isinstance(result, Exception):
                partial.append(
                    {
                        "component": name,
                        "code": result.code
                        if isinstance(result, ApiError)
                        else "dependency_unavailable",
                        "retryable": result.retryable
                        if isinstance(result, ApiError)
                        else True,
                    }
                )
                projections[name] = {}
                continue
            rows = result.get("items") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                partial.append(
                    {
                        "component": name,
                        "code": "dependency_invalid_response",
                        "retryable": False,
                    }
                )
                projections[name] = {}
                continue
            projections[name] = {
                str(row["id"]): row
                for row in rows
                if isinstance(row, dict) and row.get("id")
            }
        properties = projections.get("maintenance_properties", {})
        staff = projections.get("maintenance_assignees", {})
        enriched = []
        for item in items:
            row = dict(item)
            prop = item.get("property")
            if isinstance(prop, dict):
                projection = properties.get(str(prop.get("id")), {})
                row["property"] = {
                    **prop,
                    **{
                        key: projection[key]
                        for key in ("reference", "address", "building", "attributes")
                        if key in projection
                    },
                }
            assignee = item.get("assigned_staff")
            if isinstance(assignee, dict):
                projection = staff.get(str(assignee.get("id")), {})
                row["assigned_staff"] = (
                    {**assignee, "display_name": projection["display_name"]}
                    if projection.get("display_name")
                    else dict(assignee)
                )
            enriched.append(row)
        return {**page, "items": enriched}, partial

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
