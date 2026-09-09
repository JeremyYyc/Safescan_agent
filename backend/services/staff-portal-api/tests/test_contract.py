from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.cache import MemoryCache, private_cache_key
from app.client import Clients
from app.config import settings
from app.errors import map_downstream_error
from app.main import create_app
from app.service import PortalService


def token(role="property_manager", *, account_type="staff", subject="staff-1"):
    now = datetime.now(timezone.utc)
    permissions = (
        [
            "report:generate_all",
            "iam:staff:read",
            "lease:manage_all",
            "maintenance:manage_all",
        ]
        if role == "manager_admin"
        else ["report:generate_assigned"]
    )
    return jwt.encode(
        {
            "iss": settings.issuer,
            "aud": settings.audience,
            "sub": subject,
            "account_type": account_type,
            "role": role,
            "permissions": permissions,
            "resource_scopes": ["building:b1"],
            "av": 2,
            "rv": 3,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def handler(request: httpx.Request):
    if request.url.path == "/internal/v1/tokens/exchange":
        return httpx.Response(200, json={"data": {"access_token": "delegated-token"}})
    if request.url.path == "/api/v1/me":
        return httpx.Response(
            200, json={"data": {"id": "staff-1", "display_name": "Noah Mitchell"}}
        )
    if request.url.path.endswith("/reports") and request.method == "POST":
        assert request.headers["authorization"] == "Bearer delegated-token"
        assert request.headers["idempotency-key"] == "idem-1"
        assert request.headers["x-request-id"] == "corr-1"
        assert (
            request.headers["traceparent"]
            == "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
        )
        return httpx.Response(201, json={"data": {"id": "report-1", "status": "draft"}})
    return httpx.Response(200, json={"data": {"items": [], "total": 0}})


@pytest.fixture
async def api():
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
async def test_openapi_is_staff_only_and_declares_error_contract(api):
    client, _ = api
    schema = (await client.get("/openapi.json")).json()
    paths = schema["paths"]
    assert "/api/v1/staff/bootstrap" in paths
    assert all(not path.startswith("/api/v1/tenant") for path in paths)
    assert "ErrorEnvelope" in schema["components"]["schemas"]
    assert len([p for p in paths if p.startswith("/api/v1/staff")]) >= 30


@pytest.mark.asyncio
async def test_role_boundary_and_context_idempotency_propagation(api):
    client, _ = api
    forbidden = await client.post(
        "/api/v1/staff/properties/p1/reports",
        headers={"Authorization": f"Bearer {token('leasing_consultant')}"},
        json={},
    )
    assert (
        forbidden.status_code == 403
        and forbidden.json()["error"]["code"] == "action_forbidden"
    )
    allowed = await client.post(
        "/api/v1/staff/properties/p1/reports",
        headers={
            "Authorization": f"Bearer {token()}",
            "Idempotency-Key": "idem-1",
            "X-Request-ID": "corr-1",
            "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        },
        json={},
    )
    assert allowed.status_code == 201 and allowed.json()["data"]["id"] == "report-1"
    assert allowed.headers["x-request-id"] == "corr-1"


@pytest.mark.asyncio
async def test_framework_404_and_405_use_unified_error(api):
    client, _ = api
    missing = await client.get("/api/v1/staff/does-not-exist")
    wrong_method = await client.delete("/api/v1/staff/bootstrap")
    assert (
        missing.status_code == 404
        and missing.json()["error"]["code"] == "resource_not_found"
    )
    assert (
        wrong_method.status_code == 405
        and wrong_method.json()["error"]["code"] == "method_not_allowed"
    )


@pytest.mark.asyncio
async def test_staff_portal_rejects_customer_token(api):
    client, _ = api
    response = await client.get(
        "/api/v1/staff/bootstrap",
        headers={"Authorization": f"Bearer {token(account_type='customer')}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manager_admin_boundary(api):
    client, _ = api
    denied = await client.get(
        "/api/v1/staff/admin/staff", headers={"Authorization": f"Bearer {token()}"}
    )
    allowed = await client.get(
        "/api/v1/staff/admin/staff",
        headers={"Authorization": f"Bearer {token('manager_admin')}"},
    )
    assert denied.status_code == 403 and allowed.status_code == 200


@pytest.mark.asyncio
async def test_private_404_is_normalized(api):
    def not_found(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "report_access_denied",
                    "message": "hidden",
                    "details": {"secret": "x"},
                }
            },
        )

    clients = Clients(transport=httpx.MockTransport(not_found))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.get(
            "/api/v1/staff/reports/r1", headers={"Authorization": f"Bearer {token()}"}
        )
    await clients.close()
    body = response.json()["error"]
    assert (
        response.status_code == 404
        and body["code"] == "resource_not_found"
        and body["details"] == {}
        and body["field_errors"] == []
    )


@pytest.mark.asyncio
async def test_timeout_maps_to_504():
    def timeout(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        raise httpx.ReadTimeout("slow", request=request)

    clients = Clients(transport=httpx.MockTransport(timeout))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.get(
            "/api/v1/staff/reports/r1", headers={"Authorization": f"Bearer {token()}"}
        )
    await clients.close()
    assert (
        response.status_code == 504
        and response.json()["error"]["code"] == "dependency_timeout"
    )


@pytest.mark.asyncio
async def test_report_events_stream_is_passed_through():
    def stream(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        assert request.headers["accept"] == "application/x-ndjson"
        return httpx.Response(
            200,
            content=b'{"sequence_no":1,"type":"job.started"}\n',
            headers={"content-type": "application/x-ndjson"},
        )

    clients = Clients(transport=httpx.MockTransport(stream))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.get(
            "/api/v1/staff/report-jobs/j1/events",
            headers={
                "Authorization": f"Bearer {token()}",
                "Accept": "application/x-ndjson",
            },
        )
    await clients.close()
    assert (
        response.status_code == 200
        and response.headers["content-type"].startswith("application/x-ndjson")
        and b"job.started" in response.content
    )


@pytest.mark.asyncio
async def test_private_cache_isolated_by_subject_permissions_and_invalidated(api):
    _, cache = api
    from app.auth import Principal
    from app.models import Role

    p1 = Principal(
        "s1", Role.PROPERTY_MANAGER, frozenset({"a"}), ("b1",), 1, 1, "t", {}
    )
    p2 = Principal(
        "s2", Role.PROPERTY_MANAGER, frozenset({"a"}), ("b1",), 1, 1, "t", {}
    )
    p3 = Principal(
        "s1", Role.PROPERTY_MANAGER, frozenset({"a", "b"}), ("b1",), 1, 1, "t", {}
    )
    keys = [private_cache_key("x", p) for p in (p1, p2, p3)]
    assert len(set(keys)) == 3
    for key in keys:
        await cache.set(key, {"x": 1}, 10)
    await cache.invalidate_subject("s1")
    assert (
        await cache.get(keys[0]) is None
        and await cache.get(keys[2]) is None
        and await cache.get(keys[1]) is not None
    )


@pytest.mark.parametrize(
    "status,code,expected_status,expected_code",
    [
        (401, "invalid_token", 401, "invalid_token"),
        (403, "action_forbidden", 403, "action_forbidden"),
        (404, "order_not_found", 404, "resource_not_found"),
        (409, "version_conflict", 409, "version_conflict"),
        (422, "assignee_not_allowed", 422, "assignee_not_allowed"),
        (429, "rate_limited", 429, "rate_limited"),
        (500, "internal_error", 503, "dependency_unavailable"),
        (503, "dependency_unavailable", 503, "dependency_unavailable"),
    ],
)
def test_downstream_status_mapping(status, code, expected_status, expected_code):
    error = map_downstream_error(
        status,
        {
            "error": {
                "code": code,
                "message": "safe",
                "retryable": status in (429, 503),
                "details": {},
            }
        },
        "maintenance",
    )
    assert (error.status, error.code) == (expected_status, expected_code)


@pytest.mark.asyncio
async def test_memory_cache_honors_ttl_and_loader_is_lazy(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.cache.time.monotonic", lambda: clock[0])
    cache = MemoryCache()
    from app.auth import Principal
    from app.models import Role

    principal = Principal(
        "s1", Role.PROPERTY_MANAGER, frozenset({"a"}), (), 1, 1, "t", {}
    )
    portal = PortalService(None, cache)
    loads = 0

    async def load():
        nonlocal loads
        loads += 1
        return {"value": loads}

    assert await portal.cached("x", principal, "", 10, load) == {"value": 1}
    assert await portal.cached("x", principal, "", 10, load) == {"value": 1}
    assert loads == 1
    clock[0] = 110.0
    assert await portal.cached("x", principal, "", 10, load) == {"value": 2}


@pytest.mark.asyncio
async def test_staff_commands_match_strict_leasing_contract():
    received = {}

    def strict_leasing(request):
        if request.url.path == "/internal/v1/tokens/exchange":
            return httpx.Response(200, json={"data": {"access_token": "d"}})
        received[request.url.path] = __import__("json").loads(request.content)
        resource = "lease-1" if "/leases/" in request.url.path else "application-1"
        return httpx.Response(200, json={"data": {"id": resource}})

    clients = Clients(transport=httpx.MockTransport(strict_leasing))
    app = create_app(clients=clients, cache=MemoryCache())
    headers = {
        "Authorization": f"Bearer {token('manager_admin')}",
        "Idempotency-Key": "idem",
    }
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        start = await client.post(
            "/api/v1/staff/applications/a1/start-review",
            headers=headers,
            json={"version": 1},
        )
        approve = await client.post(
            "/api/v1/staff/applications/a1/approve",
            headers=headers,
            json={"version": 2, "decision_note": "ok"},
        )
        reject_missing_reason = await client.post(
            "/api/v1/staff/applications/a1/reject",
            headers=headers,
            json={"version": 2},
        )
        send = await client.post(
            "/api/v1/staff/leases/l1/send-for-signature",
            headers=headers,
            json={"version": 1, "lease_document_id": "doc-1"},
        )
        invalid_signature = await client.post(
            "/api/v1/staff/leases/l1/company-signature",
            headers=headers,
            json={
                "version": 1,
                "lease_document_id": "doc-1",
                "terms_digest": "12345678",
                "accepted": False,
            },
        )
    await clients.close()

    assert start.status_code == approve.status_code == send.status_code == 200
    assert reject_missing_reason.status_code == invalid_signature.status_code == 422
    assert received["/internal/v1/applications/a1/start-review"] == {"version": 1}
    assert received["/internal/v1/applications/a1/approve"] == {
        "version": 2,
        "decision_note": "ok",
    }
    assert received["/internal/v1/leases/l1/send-for-signature"] == {
        "version": 1,
        "lease_document_id": "doc-1",
    }
