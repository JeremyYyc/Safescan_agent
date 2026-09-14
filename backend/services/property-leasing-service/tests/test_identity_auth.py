import os
from unittest.mock import Mock, patch

import jwt
import pytest

os.environ.setdefault("PROPERTY_LEASING_DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-at-least-24-characters")

from app.clients.identity import IdentityClient
from app.clients.service_token import IdentityServiceTokenProvider, SERVICE_SCOPES
from app.core.config import Settings
from app import outbox_worker


SECRET = "identity-signing-secret-at-least-24-characters"


def settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://x:x@localhost/x",
        "jwt_secret": "test-secret-that-is-at-least-24-characters",
        "identity_service_credential": SECRET,
        "identity_service_token_seconds": 60,
        "identity_token_refresh_skew_seconds": 10,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_requires_a_refreshable_identity_credential() -> None:
    configured = settings(identity_service_credential="", identity_service_token="legacy-token")
    with pytest.raises(RuntimeError, match="PROPERTY_LEASING_IDENTITY_CREDENTIAL"):
        configured.validate_runtime()


def test_short_lived_token_has_fixed_identity_boundary_and_refreshes() -> None:
    now = [1_000.0]
    provider = IdentityServiceTokenProvider(settings(), clock=lambda: now[0])

    first = provider.token()
    first_claims = jwt.decode(first, SECRET, algorithms=["HS256"],
                              audience="safescan-identity-internal",
                              options={"verify_exp": False})
    assert first_claims["sub"] == "service:property-leasing"
    assert first_claims["scopes"] == list(SERVICE_SCOPES)
    assert first_claims["exp"] - first_claims["iat"] == 60
    assert provider.token() == first

    now[0] = 1_051.0
    refreshed = provider.token()
    assert refreshed != first
    refreshed_claims = jwt.decode(refreshed, SECRET, algorithms=["HS256"],
                                  audience="safescan-identity-internal",
                                  options={"verify_exp": False})
    assert refreshed_claims["iat"] == 1_051


def test_identity_client_refreshes_once_after_unauthorized() -> None:
    tokens = Mock()
    tokens.refreshable = True
    tokens.token.side_effect = ["first", "second"]
    unauthorized = Mock(status_code=401)
    success = Mock(status_code=200)
    success.json.return_value = {"data": {"items": []}}

    with patch("app.clients.identity.httpx.get", side_effect=[unauthorized, success]) as request:
        IdentityClient(settings(), tokens).check_readiness()

    assert request.call_count == 2
    tokens.invalidate.assert_called_once_with()
    assert request.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer first"
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer second"


def test_identity_outbox_delivery_refreshes_once_after_unauthorized() -> None:
    tokens = Mock()
    tokens.refreshable = True
    tokens.token.side_effect = ["first", "second"]
    unauthorized = Mock(status_code=401)
    success = Mock(status_code=202)
    success.raise_for_status.return_value = None

    with (
        patch.object(outbox_worker, "_identity_tokens", tokens),
        patch("app.outbox_worker.httpx.post", side_effect=[unauthorized, success]) as request,
    ):
        outbox_worker._post(
            "http://identity/internal/v1/customer-status-events",
            {"event_id": "event"},
            identity_target=True,
        )

    assert request.call_count == 2
    tokens.invalidate.assert_called_once_with()
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer second"


def test_static_token_rejects_wrong_audience_before_use() -> None:
    token = jwt.encode(
        {"sub": "service:property-leasing", "iss": "safescan-identity",
         "aud": "wrong", "scopes": list(SERVICE_SCOPES), "exp": 2_000},
        SECRET, algorithm="HS256",
    )
    provider = IdentityServiceTokenProvider(
        settings(app_env="development", identity_service_credential="",
                 identity_service_token=token),
        clock=lambda: 1_000,
    )
    with pytest.raises(RuntimeError, match="wrong audience"):
        provider.token()
