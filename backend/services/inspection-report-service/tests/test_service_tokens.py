from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from safescan_common.auth import ServiceTokenError, ServiceTokenProvider
from safescan_common.http.errors import ApiError

import inspection_report_service.main as main_module
from inspection_report_service.auth import Principal
from inspection_report_service.clients import IDENTITY_CLIENT_SCOPES, PropertyLeasingClient
from inspection_report_service.config import Settings


def settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": SecretStr("postgresql+psycopg://x:x@localhost/test"),
        "jwt_secret": SecretStr("actor-verification-secret-long-enough"),
        "identity_client_secret": SecretStr("identity-client-secret-long-enough"),
        "minio_access_key": SecretStr("x"),
        "minio_secret_key": SecretStr("x"),
    }
    values.update(overrides)
    return Settings(**values)


def actor() -> Principal:
    return Principal(
        uuid4(), "staff", frozenset({"report:read_all"}), "incoming-actor-token",
        staff_id=uuid4(), role="manager_admin",
    )


def test_shared_service_token_refresh_and_property_consumer_contract(monkeypatch) -> None:
    now = [100.0]
    service_token_calls = 0
    exchange_calls = []

    def identity_handler(request: httpx.Request) -> httpx.Response:
        nonlocal service_token_calls
        service_token_calls += 1
        assert request.url.path == "/internal/v1/service-tokens"
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, json={"data": {
            "access_token": f"identity-service-token-{service_token_calls:02d}",
            "expires_in": 60,
        }})

    provider = ServiceTokenProvider(
        "http://identity", "inspection-report",
        "identity-client-secret-long-enough", IDENTITY_CLIENT_SCOPES,
        transport=httpx.MockTransport(identity_handler), clock=lambda: now[0],
    )

    def post(url, **kwargs):
        exchange_calls.append(kwargs)
        return httpx.Response(
            200,
            json={"data": {"access_token": "property-actor-token-long-enough"}},
            request=httpx.Request("POST", url),
        )

    def request(method, url, **kwargs):
        return httpx.Response(
            200,
            json={"data": {
                "allowed": True,
                "property_id": str(property_id),
                "active_lease_id": str(uuid4()),
            }},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "request", request)
    property_id = uuid4()
    client = PropertyLeasingClient(settings(), provider)

    assert client.property_access(actor(), property_id, "report:read")["allowed"]
    assert service_token_calls == 1
    assert exchange_calls[0]["json"]["requested_scopes"] == []
    assert exchange_calls[0]["headers"]["Authorization"].endswith("-01")

    now[0] = 148.0
    assert client.property_access(actor(), property_id, "report:read")["allowed"]
    assert service_token_calls == 2
    assert exchange_calls[1]["headers"]["Authorization"].endswith("-02")
    provider.close()


def test_report_requests_only_required_identity_service_scopes() -> None:
    assert IDENTITY_CLIENT_SCOPES == (
        "identity:token_exchange",
        "report:read_work_context",
        "work_order:read_assigned",
    )


def test_formal_runtime_rejects_missing_credential_and_never_falls_back(
    monkeypatch,
) -> None:
    config = settings(identity_client_secret=SecretStr(""))
    with pytest.raises(RuntimeError, match="IDENTITY_CLIENT_SECRET"):
        config.validate_runtime()

    class MissingTokens:
        @staticmethod
        def get() -> str:
            raise ServiceTokenError(401)

    called = False

    def request(*args, **kwargs):
        nonlocal called
        called = True
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(ApiError) as caught:
        PropertyLeasingClient(config, MissingTokens()).property_access(
            actor(), uuid4(), "report:read"
        )
    assert (caught.value.status_code, caught.value.code) == (
        503,
        "dependency_unavailable",
    )
    assert called is False


def test_formal_api_startup_fails_fast_when_identity_cannot_issue_token(
    monkeypatch,
) -> None:
    config = settings()

    class MissingCredentialClient:
        @staticmethod
        def require_identity_service_token() -> str:
            raise RuntimeError("Identity service credential is unavailable")

    monkeypatch.setattr(main_module, "get_settings", lambda: config)
    monkeypatch.setattr(main_module, "leasing_client", MissingCredentialClient)

    with pytest.raises(RuntimeError, match="service credential is unavailable"):
        with TestClient(main_module.app):
            pass
