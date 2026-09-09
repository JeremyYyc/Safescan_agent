from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

import httpx

from .auth import Principal
from .config import settings
from .errors import ApiError, map_downstream_error


@dataclass(frozen=True)
class RequestContext:
    correlation_id: str
    traceparent: str | None
    idempotency_key: str | None


class DownstreamClient:
    """Pooled downstream HTTP client; inject ``httpx.MockTransport`` in tests."""

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        audience: str | None = None,
        identity: "IdentityClient | None" = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        timeout = httpx.Timeout(
            settings.request_timeout, connect=settings.connect_timeout
        )
        limits = httpx.Limits(
            max_connections=settings.pool_connections,
            max_keepalive_connections=settings.pool_keepalive,
        )
        self.name = name
        self.audience = audience
        self.identity = identity
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, limits=limits, transport=transport
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        principal: Principal,
        context: RequestContext,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | AsyncIterator[bytes] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self.identity and self.audience:
            principal = replace(
                principal,
                bearer=await self.identity.exchange(principal, self.audience, context),
            )
        request_headers = {
            "Authorization": f"Bearer {principal.bearer}",
            "X-Request-ID": context.correlation_id,
            "X-Actor-Subject": principal.subject,
        }
        if context.traceparent:
            request_headers["traceparent"] = context.traceparent
        if context.idempotency_key:
            request_headers["Idempotency-Key"] = context.idempotency_key
        if headers:
            request_headers.update(headers)
        try:
            response = await self._http.request(
                method,
                path,
                params=params,
                json=json,
                content=content,
                headers=request_headers,
            )
        except httpx.TimeoutException as exc:
            raise ApiError(
                504,
                "dependency_timeout",
                "A dependency timed out",
                retryable=True,
                details={
                    "dependency": self.name,
                    "timeout_ms": int(settings.request_timeout * 1000),
                },
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(
                503,
                "dependency_unavailable",
                "A dependency is unavailable",
                retryable=True,
                details={"dependency": self.name},
            ) from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            raise map_downstream_error(response.status_code, payload, self.name)
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                502,
                "dependency_invalid_response",
                "A dependency returned an invalid response",
                details={"dependency": self.name},
            ) from exc
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    async def stream(
        self,
        method: str,
        path: str,
        *,
        principal: Principal,
        context: RequestContext,
        body: AsyncIterator[bytes],
        headers: dict[str, str],
    ) -> httpx.Response:
        if self.identity and self.audience:
            principal = replace(
                principal,
                bearer=await self.identity.exchange(principal, self.audience, context),
            )
        request_headers = {
            "Authorization": f"Bearer {principal.bearer}",
            "X-Request-ID": context.correlation_id,
            "X-Actor-Subject": principal.subject,
            **headers,
        }
        if context.traceparent:
            request_headers["traceparent"] = context.traceparent
        if context.idempotency_key:
            request_headers["Idempotency-Key"] = context.idempotency_key
        request = self._http.build_request(
            method, path, headers=request_headers, content=body
        )
        try:
            response = await self._http.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise ApiError(
                504,
                "dependency_timeout",
                "A dependency timed out",
                retryable=True,
                details={"dependency": self.name},
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(
                503,
                "dependency_unavailable",
                "A dependency is unavailable",
                retryable=True,
                details={"dependency": self.name},
            ) from exc
        if response.status_code >= 400:
            raw = await response.aread()
            await response.aclose()
            try:
                payload = httpx.Response(response.status_code, content=raw).json()
            except ValueError:
                payload = None
            raise map_downstream_error(response.status_code, payload, self.name)
        return response

    async def open_stream(
        self,
        path: str,
        *,
        principal: Principal,
        context: RequestContext,
        params: dict[str, Any] | None = None,
        accept: str = "text/event-stream",
    ) -> httpx.Response:
        if self.identity and self.audience:
            principal = replace(
                principal,
                bearer=await self.identity.exchange(principal, self.audience, context),
            )
        headers = {
            "Authorization": f"Bearer {principal.bearer}",
            "X-Request-ID": context.correlation_id,
            "X-Actor-Subject": principal.subject,
            "Accept": accept,
        }
        if context.traceparent:
            headers["traceparent"] = context.traceparent
        request = self._http.build_request("GET", path, params=params, headers=headers)
        try:
            response = await self._http.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise ApiError(
                504,
                "dependency_timeout",
                "A dependency timed out",
                retryable=True,
                details={"dependency": self.name},
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(
                503,
                "dependency_unavailable",
                "A dependency is unavailable",
                retryable=True,
                details={"dependency": self.name},
            ) from exc
        if response.status_code >= 400:
            raw = await response.aread()
            await response.aclose()
            try:
                payload = httpx.Response(response.status_code, content=raw).json()
            except ValueError:
                payload = None
            raise map_downstream_error(response.status_code, payload, self.name)
        return response


class IdentityClient(DownstreamClient):
    def __init__(self, **kwargs: Any):
        super().__init__("identity", settings.identity_url, **kwargs)

    async def exchange(
        self, principal: Principal, target_audience: str, context: RequestContext
    ) -> str:
        prefixes = {
            "property-leasing-service": (
                "property:",
                "prospect:",
                "application:",
                "lease:",
                "building:",
                "scope:",
            ),
            "maintenance-service": ("maintenance:", "work_order:", "property:"),
            "inspection-report-service": ("report:", "property:"),
        }.get(target_audience, ())
        requested_scopes = sorted(
            scope for scope in principal.permissions if scope.startswith(prefixes)
        )
        headers = {
            "Authorization": f"Bearer {settings.service_token}",
            "X-Request-ID": context.correlation_id,
        }
        if context.traceparent:
            headers["traceparent"] = context.traceparent
        try:
            response = await self._http.post(
                "/internal/v1/tokens/exchange",
                headers=headers,
                json={
                    "user_token": principal.bearer,
                    "target_audience": target_audience,
                    "requested_scopes": requested_scopes,
                },
            )
        except httpx.TimeoutException as exc:
            raise ApiError(
                504,
                "dependency_timeout",
                "Identity token exchange timed out",
                retryable=True,
                details={"dependency": "identity"},
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(
                503,
                "dependency_unavailable",
                "Identity is unavailable",
                retryable=True,
                details={"dependency": "identity"},
            ) from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            raise map_downstream_error(response.status_code, payload, "identity")
        try:
            data = response.json().get("data", response.json())
            return str(data["access_token"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiError(
                502,
                "dependency_invalid_response",
                "Identity returned an invalid token exchange response",
                details={"dependency": "identity"},
            ) from exc


class PropertyLeasingClient(DownstreamClient):
    def __init__(self, **kwargs: Any):
        super().__init__(
            "property-leasing",
            settings.leasing_url,
            audience="property-leasing-service",
            **kwargs,
        )


class MaintenanceClient(DownstreamClient):
    def __init__(self, **kwargs: Any):
        super().__init__(
            "maintenance",
            settings.maintenance_url,
            audience="maintenance-service",
            **kwargs,
        )


class InspectionReportClient(DownstreamClient):
    def __init__(self, **kwargs: Any):
        super().__init__(
            "inspection-report",
            settings.report_url,
            audience="inspection-report-service",
            **kwargs,
        )


class Clients:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.identity = IdentityClient(transport=transport)
        self.leasing = PropertyLeasingClient(transport=transport)
        self.leasing.identity = self.identity
        self.maintenance = MaintenanceClient(transport=transport)
        self.maintenance.identity = self.identity
        self.report = InspectionReportClient(transport=transport)
        self.report.identity = self.identity

    async def close(self) -> None:
        for client in (self.identity, self.leasing, self.maintenance, self.report):
            await client.close()
