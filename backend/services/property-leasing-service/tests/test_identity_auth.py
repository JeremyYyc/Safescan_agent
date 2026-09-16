import os
from unittest.mock import Mock, patch

import pytest
from safescan_common.auth import ServiceTokenError
from safescan_common.http.errors import ApiError

os.environ.setdefault("PROPERTY_LEASING_DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-at-least-24-characters")

from app import outbox_worker
from app.clients.identity import IdentityClient
from app.core.config import Settings


def settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://x:x@localhost/x",
        "jwt_secret": "test-secret-that-is-at-least-24-characters",
        "identity_client_secret": "identity-client-secret-at-least-24-characters",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_requires_identity_client_secret() -> None:
    configured = settings(identity_client_secret="")
    with pytest.raises(RuntimeError, match="IDENTITY_CLIENT_SECRET"):
        configured.validate_runtime()


def test_identity_client_refreshes_once_after_unauthorized() -> None:
    tokens = Mock()
    tokens.get.side_effect = ["first", "second"]
    unauthorized = Mock(status_code=401)
    success = Mock(status_code=200)
    success.json.return_value = {"data": {"items": []}}

    with patch("app.clients.identity.httpx.get", side_effect=[unauthorized, success]) as request:
        IdentityClient(settings(), tokens).check_readiness()

    assert request.call_count == 2
    tokens.invalidate.assert_called_once_with("first")
    assert request.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer first"
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer second"


def test_identity_client_maps_exchange_failure_without_dependency_call() -> None:
    tokens = Mock()
    tokens.get.side_effect = ServiceTokenError(401)

    with patch("app.clients.identity.httpx.get") as request:
        with pytest.raises(ApiError) as caught:
            IdentityClient(settings(), tokens).check_readiness()

    assert (caught.value.status_code, caught.value.code) == (503, "dependency_unavailable")
    request.assert_not_called()


def test_identity_outbox_delivery_refreshes_once_after_unauthorized() -> None:
    tokens = Mock()
    tokens.get.side_effect = ["first", "second"]
    identity = IdentityClient(settings(), tokens)
    unauthorized = Mock(status_code=401)
    success = Mock(status_code=202)
    success.raise_for_status.return_value = None

    with (
        patch.object(outbox_worker, "_identity", identity),
        patch("app.outbox_worker.httpx.post", side_effect=[unauthorized, success]) as request,
    ):
        outbox_worker._post(
            "http://identity/internal/v1/customer-status-events",
            {"event_id": "event"},
            identity_target=True,
        )

    assert request.call_count == 2
    tokens.invalidate.assert_called_once_with("first")
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer second"


def test_identity_outbox_maps_exchange_failure_to_dependency_unavailable() -> None:
    tokens = Mock()
    tokens.get.side_effect = ServiceTokenError(401)
    identity = IdentityClient(settings(), tokens)

    with patch.object(outbox_worker, "_identity", identity):
        with pytest.raises(ApiError) as caught:
            outbox_worker._post(
                "http://identity/internal/v1/customer-status-events",
                {"event_id": "event"},
                identity_target=True,
            )

    assert caught.value.status_code == 503
