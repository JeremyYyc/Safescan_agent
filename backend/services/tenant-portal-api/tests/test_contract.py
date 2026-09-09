from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.cache import MemoryCache, cache_key
from app.client import Clients
from app.config import settings
from app.main import create_app


def token(status="tenant", subject="customer-1", account_type="customer"):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": settings.issuer,
            "aud": settings.audience,
            "sub": subject,
            "account_type": account_type,
            "customer_status": status,
            "scopes": [
                "property:read_market",
                "application:self:create",
                "application:self:submit",
                "maintenance:self:create",
                "report:self:create",
            ],
            "av": 2,
            "csv": 4,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


seen = []


def handler(request: httpx.Request):
    seen.append((request.method, request.url.path, dict(request.headers)))
    if request.url.path == "/internal/v1/tokens/exchange":
        return httpx.Response(200, json={"data": {"access_token": "delegated"}})
    if request.url.path == "/api/v1/me":
        return httpx.Response(
            200, json={"data": {"id": "customer-1", "username": "Taylor"}}
        )
    if request.url.path == "/internal/v1/leases":
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "id": "lease-1",
                            "status": "active",
                            "property": {"id": "property-1"},
                        }
                    ]
                }
            },
        )
    if (
        request.url.path == "/internal/v1/maintenance-orders"
        and request.method == "POST"
    ):
        body = __import__("json").loads(request.content)
        assert body["lease_id"] == "lease-1" and body["property_id"] == "property-1"
        return httpx.Response(201, json={"data": {"id": "order-1"}})
    if (
        request.url.path == "/internal/v1/properties/property-1/reports"
        and request.method == "POST"
    ):
        assert (
            request.headers["authorization"] == "Bearer delegated"
            and request.headers["idempotency-key"] == "idem-tenant"
        )
        return httpx.Response(201, json={"data": {"id": "report-1"}})
    return httpx.Response(200, json={"data": {"items": []}})


@pytest.fixture
async def api():
    seen.clear()
    clients = Clients(transport=httpx.MockTransport(handler))
    cache = MemoryCache()
    app = create_app(clients=clients, cache=cache)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        yield client, cache
    await clients.close()


@pytest.mark.asyncio
async def test_openapi_is_tenant_only(api):
    client, _ = api
    schema = (await client.get("/openapi.json")).json()
    paths = schema["paths"]
    assert "/api/v1/tenant/bootstrap" in paths and all(
        not p.startswith("/api/v1/staff") for p in paths
    )
    assert "ErrorEnvelope" in schema["components"]["schemas"]
    assert len([p for p in paths if p.startswith("/api/v1/tenant")]) >= 25


@pytest.mark.asyncio
async def test_guest_public_only(api):
    client, _ = api
    assert (await client.get("/api/v1/tenant/properties")).status_code == 200
    assert (await client.get("/api/v1/tenant/applications")).status_code == 401


@pytest.mark.asyncio
async def test_active_tenant_derives_authority_fields_and_propagates_idempotency(api):
    client, _ = api
    headers = {
        "Authorization": f"Bearer {token()}",
        "Idempotency-Key": "idem-tenant",
        "X-Request-ID": "cid-t",
    }
    order = await client.post(
        "/api/v1/tenant/maintenance-orders",
        headers=headers,
        json={"summary": "Leak", "priority": "high"},
    )
    report = await client.post(
        "/api/v1/tenant/my-property/reports", headers=headers, json={"title": "Move-in"}
    )
    assert (
        order.status_code == 201
        and report.status_code == 201
        and report.headers["x-request-id"] == "cid-t"
    )


@pytest.mark.asyncio
async def test_former_tenant_is_read_only_for_reports(api):
    client, _ = api
    response = await client.post(
        "/api/v1/tenant/my-property/reports",
        headers={"Authorization": f"Bearer {token('former_tenant')}"},
        json={},
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "action_forbidden"
    )


@pytest.mark.asyncio
async def test_executed_not_active_tenant_cannot_repair_or_report():
    def executed(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        if request.url.path == "/internal/v1/leases":
            return httpx.Response(200, json={"data": {"items": []}})
        return httpx.Response(
            500, json={"error": {"code": "unexpected_call", "message": "unexpected"}}
        )

    clients = Clients(transport=httpx.MockTransport(executed))
    app = create_app(clients=clients, cache=MemoryCache())
    headers = {"Authorization": f"Bearer {token()}"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        repair = await client.post(
            "/api/v1/tenant/maintenance-orders",
            headers=headers,
            json={"summary": "Leak", "priority": "high"},
        )
        report = await client.post(
            "/api/v1/tenant/my-property/reports", headers=headers, json={}
        )
    await clients.close()
    assert (
        repair.status_code == 403
        and repair.json()["error"]["code"] == "current_lease_required"
    )
    assert (
        report.status_code == 403
        and report.json()["error"]["code"] == "current_lease_required"
    )


@pytest.mark.asyncio
async def test_browser_cannot_supply_lease_property_or_subject(api):
    client, _ = api
    response = await client.post(
        "/api/v1/tenant/maintenance-orders",
        headers={"Authorization": f"Bearer {token()}"},
        json={"summary": "Leak", "priority": "high", "lease_id": "forged"},
    )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "validation_failed"
    )


@pytest.mark.asyncio
async def test_cache_key_isolates_subject_and_status_version(api):
    from app.auth import Principal
    from app.models import CustomerStatus

    a = Principal("a", CustomerStatus.TENANT, frozenset({"x"}), 1, 1, "t", {})
    b = Principal("b", CustomerStatus.TENANT, frozenset({"x"}), 1, 1, "t", {})
    stale = Principal("a", CustomerStatus.TENANT, frozenset({"x"}), 1, 2, "t", {})
    assert len({cache_key("home", p) for p in (a, b, stale)}) == 3


@pytest.mark.asyncio
async def test_downstream_404_shape_hides_resource_existence():
    def hidden(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "lease_access_required",
                    "message": "secret",
                    "details": {"id": "x"},
                }
            },
        )

    clients = Clients(transport=httpx.MockTransport(hidden))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.get(
            "/api/v1/tenant/leases/other",
            headers={"Authorization": f"Bearer {token()}"},
        )
    await clients.close()
    body = response.json()["error"]
    assert (
        response.status_code == 404
        and body["code"] == "resource_not_found"
        and body["details"] == {}
        and body["field_errors"] == []
    )
