from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from safescan_common.http.errors import ApiError

import inspection_report_service.main as main_module
from inspection_report_service.auth import Principal
from inspection_report_service.clients import PropertyLeasingClient
from inspection_report_service.config import Settings
from inspection_report_service.service_tokens import IdentityServiceTokenProvider


def settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": SecretStr("postgresql+psycopg://x:x@localhost/test"),
        "jwt_secret": SecretStr("actor-verification-secret-long-enough"),
        "identity_service_credential": SecretStr("identity-service-signing-secret-long-enough"),
        "identity_service_token_seconds": 60,
        "identity_service_token_refresh_skew_seconds": 10,
        "minio_access_key": SecretStr("x"),
        "minio_secret_key": SecretStr("x"),
    }
    values.update(overrides)
    return Settings(**values)


def test_short_lived_identity_service_token_is_cached_then_refreshed() -> None:
    now = [1_000.0]
    config = settings()
    provider = IdentityServiceTokenProvider(config, clock=lambda: now[0])

    first = provider.require_token()
    assert provider.require_token() == first
    claims = jwt.decode(
        first,
        config.identity_service_credential.get_secret_value(),
        algorithms=["HS256"],
        audience=config.identity_internal_audience,
        issuer=config.jwt_issuer,
        options={"verify_exp": False},
    )
    assert claims["sub"] == "service:inspection-report"
    assert claims["scopes"] == [
        "identity:token_exchange",
        "report:read_work_context",
        "work_order:read_assigned",
    ]
    assert claims["exp"] == 1_060

    now[0] = 1_049.0
    assert provider.require_token() == first
    now[0] = 1_050.0
    refreshed = provider.require_token()
    assert refreshed != first
    refreshed_claims = jwt.decode(
        refreshed,
        config.identity_service_credential.get_secret_value(),
        algorithms=["HS256"],
        audience=config.identity_internal_audience,
        issuer=config.jwt_issuer,
        options={"verify_exp": False},
    )
    assert refreshed_claims["exp"] == 1_110


def test_invalid_configured_token_is_replaced_in_formal_runtime() -> None:
    config = settings(
        identity_service_token=SecretStr(
            jwt.encode(
                {
                    "aud": "safescan-identity-internal",
                    "exp": 4_000_000_000,
                    "iat": 1_000,
                    "iss": "safescan-identity",
                    "jti": "invalid-static-token",
                    "nbf": 1_000,
                    "scopes": list(IdentityServiceTokenProvider.required_scopes),
                    "sub": "service:inspection-report",
                },
                "wrong-signing-secret-that-is-long-enough",
                algorithm="HS256",
            )
        ),
    )
    token = IdentityServiceTokenProvider(config, clock=lambda: 1_100).require_token()
    claims = jwt.decode(
        token,
        config.identity_service_credential.get_secret_value(),
        algorithms=["HS256"],
        audience=config.identity_internal_audience,
        issuer=config.jwt_issuer,
        options={"verify_exp": False},
    )
    assert claims["jti"] != "invalid-static-token"


def test_formal_api_startup_fails_fast_without_service_credential(monkeypatch) -> None:
    config = settings(identity_service_credential=SecretStr(""))

    class MissingCredentialClient:
        @staticmethod
        def require_identity_service_token() -> str:
            raise RuntimeError("Identity service credential is unavailable")

    monkeypatch.setattr(main_module, "get_settings", lambda: config)
    monkeypatch.setattr(main_module, "leasing_client", MissingCredentialClient)

    with pytest.raises(RuntimeError, match="service credential is unavailable"):
        with TestClient(main_module.app):
            pass


def test_formal_runtime_rejects_missing_service_credential_and_actor_fallback(
    monkeypatch,
) -> None:
    config = settings(identity_service_credential=SecretStr(""))
    with pytest.raises(RuntimeError, match="IDENTITY_SERVICE_CREDENTIAL"):
        config.validate_runtime()

    called = False

    def request(*args, **kwargs):
        nonlocal called
        called = True
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "request", request)
    actor = Principal(
        uuid4(), "staff", frozenset({"report:read_all"}), "incoming-actor-token",
        staff_id=uuid4(), role="manager_admin",
    )
    with pytest.raises(ApiError) as caught:
        PropertyLeasingClient(config).property_access(actor, uuid4(), "report:read")
    assert (caught.value.status_code, caught.value.code) == (
        503,
        "dependency_unavailable",
    )
    assert called is False


def test_development_can_explicitly_use_legacy_actor_token_fallback(monkeypatch) -> None:
    config = settings(app_env="development", identity_service_credential=SecretStr(""))
    captured = {}

    def request(method, url, **kwargs):
        captured["authorization"] = kwargs["headers"]["Authorization"]
        return httpx.Response(
            200,
            json={"data": {"allowed": True, "property_id": str(property_id)}},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", request)
    actor = Principal(
        uuid4(), "staff", frozenset({"report:read_all"}), "development-actor-token",
        staff_id=uuid4(), role="manager_admin",
    )
    property_id = uuid4()
    assert PropertyLeasingClient(config).property_access(actor, property_id, "report:read")[
        "allowed"
    ]
    assert captured["authorization"] == "Bearer development-actor-token"
