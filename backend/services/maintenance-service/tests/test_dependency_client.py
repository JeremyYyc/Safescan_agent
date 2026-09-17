from uuid import uuid4

import httpx
import pytest
from app.clients.dependencies import DependencyClient
from app.core.config import Settings
from app.domain.principal import Principal
from safescan_common.http.errors import ApiError

pytestmark = [pytest.mark.unit, pytest.mark.mocked_dependency]


def settings():
    return Settings(
        database_url="postgresql+psycopg://x:x@localhost/x",
        jwt_secret="test-secret-that-is-at-least-24-characters",
        identity_client_secret="maintenance-client-secret-long-enough",
    )


def actor():
    return Principal(
        subject_id=uuid4(),
        account_type="customer",
        scopes=frozenset({"maintenance:self:create"}),
        claims={},
        customer_status="tenant",
        bearer="maintenance-audience-actor-token-long-enough",
    )


class Tokens:
    def __init__(self, *tokens):
        self.tokens = list(tokens or ("maintenance-service-token-long-enough",))
        self.index = 0
        self.invalidations = 0

    def get(self):
        return self.tokens[min(self.index, len(self.tokens) - 1)]

    def invalidate(self, rejected_token=None):
        assert rejected_token == self.get()
        self.invalidations += 1
        self.index += 1


def test_property_authorization_uses_identity_exchange_token(monkeypatch):
    calls = []
    lease_id, property_id = uuid4(), uuid4()

    def request(method, url, headers, timeout, **kwargs):
        calls.append((url, headers["Authorization"], kwargs.get("json")))
        if url.endswith("/tokens/exchange"):
            return httpx.Response(
                200, json={"data": {"access_token": "property-actor-token-long-enough"}}
            )
        return httpx.Response(
            200,
            json={
                "allowed": True,
                "lease_id": str(lease_id),
                "property_id": str(property_id),
                "status": "active",
                "lease_version": 4,
                "relationship_version": 2,
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    result = DependencyClient(settings(), Tokens()).lease_access(
        actor(), lease_id, property_id
    )
    assert result["allowed"] is True
    assert calls[0][1] == "Bearer maintenance-service-token-long-enough"
    assert calls[0][2]["target_audience"] == "property-leasing-service"
    assert calls[0][2]["user_token"] == "maintenance-audience-actor-token-long-enough"
    assert calls[0][2]["requested_scopes"] == []
    assert calls[1][1] == "Bearer property-actor-token-long-enough"


def test_missing_service_credential_fails_closed_without_property_call(monkeypatch):
    called = False

    def request(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not call dependency")

    monkeypatch.setattr(httpx, "request", request)
    config = Settings(
        database_url="postgresql+psycopg://x:x@localhost/x",
        jwt_secret="test-secret-that-is-at-least-24-characters",
        identity_client_secret="",
    )
    with pytest.raises(ApiError) as caught:
        DependencyClient(config).property_access(
            actor(), uuid4(), "maintenance:read_assigned"
        )
    assert (caught.value.status_code, caught.value.code) == (
        503,
        "dependency_unavailable",
    )
    assert called is False


def test_staff_projection_uses_staff_public_id_endpoint(monkeypatch):
    staff_id = uuid4()

    def request(method, url, headers, timeout, **kwargs):
        assert url.endswith(f"/internal/v1/staff/{staff_id}")
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": str(staff_id),
                    "status": "active",
                    "employment_status": "active",
                    "role": "maintainer",
                }
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    assert (
        DependencyClient(settings(), Tokens()).require_active_maintainer(staff_id)["role"]
        == "maintainer"
    )


def test_expired_identity_service_token_is_refreshed_once(monkeypatch):
    authorizations = []
    lease_id, property_id = uuid4(), uuid4()
    tokens = Tokens("expired-maintenance-service-token", "fresh-maintenance-service-token")

    def request(method, url, headers, timeout, **kwargs):
        authorizations.append(headers["Authorization"])
        if url.endswith("/tokens/exchange") and len(authorizations) == 1:
            return httpx.Response(401, json={"error": {"code": "invalid_token"}})
        if url.endswith("/tokens/exchange"):
            return httpx.Response(
                200, json={"data": {"access_token": "property-actor-token-long-enough"}}
            )
        return httpx.Response(
            200,
            json={
                "allowed": True,
                "lease_id": str(lease_id),
                "property_id": str(property_id),
                "status": "active",
                "lease_version": 4,
                "relationship_version": 2,
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    result = DependencyClient(settings(), tokens).lease_access(
        actor(), lease_id, property_id
    )

    assert result["allowed"] is True
    assert tokens.invalidations == 1
    assert authorizations == [
        "Bearer expired-maintenance-service-token",
        "Bearer fresh-maintenance-service-token",
        "Bearer property-actor-token-long-enough",
    ]
