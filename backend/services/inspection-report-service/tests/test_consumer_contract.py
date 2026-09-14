from uuid import uuid4

import httpx
from pydantic import SecretStr

from inspection_report_service.auth import Principal
from inspection_report_service.clients import MaintenanceClient, PropertyLeasingClient
from inspection_report_service.config import Settings


def settings() -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://x:x@localhost/test"),
        jwt_secret=SecretStr("report-test-secret-that-is-long-enough"),
        identity_client_secret=SecretStr("service-credential"),
        minio_access_key=SecretStr("x"), minio_secret_key=SecretStr("x"),
    )


class Tokens:
    def get(self):
        return "service-token"


def principal(scopes=None):
    return Principal(uuid4(), "staff", frozenset(scopes or {"report:read_assigned"}),
                     "actor-token", staff_id=uuid4(), role="property_manager")


def response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "http://contract.test"))


def test_identity_exchange_and_property_access_consumer_contract(monkeypatch) -> None:
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return response(200, {"access_token": "delegated-property-token"})

    def request(method, url, **kwargs):
        calls.append((url, kwargs.get("json") or kwargs.get("params")))
        if url.endswith("property-access:check"):
            assert kwargs["headers"]["Authorization"] == "Bearer delegated-property-token"
            return response(200, {"data": {"allowed": True, "active_lease_id": str(uuid4())}})
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "request", request)
    actor, property_id = principal(), uuid4()
    result = PropertyLeasingClient(settings(), Tokens()).property_access(actor, property_id, "report:read")
    assert result["allowed"] is True
    assert calls[0][1]["user_token"] == "actor-token"
    assert calls[0][1]["target_audience"] == "property-leasing-service"
    assert calls[1][1] == {
        "subject_id": str(actor.subject_id), "property_id": str(property_id), "action": "report:read",
    }


def test_lease_history_consumer_passes_all_authoritative_ids(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response(200, {"access_token": "lease-token"}))
    captured = {}

    def request(method, url, **kwargs):
        captured.update(kwargs["json"])
        return response(200, {"allowed": True, "status": "ended"})

    monkeypatch.setattr(httpx, "request", request)
    actor, lease_id, property_id = principal(), uuid4(), uuid4()
    result = PropertyLeasingClient(settings(), Tokens()).lease_access(
        actor, lease_id, property_id, "report:read_history"
    )
    assert result["status"] == "ended"
    assert captured == {
        "subject_id": str(actor.subject_id), "lease_id": str(lease_id),
        "property_id": str(property_id), "action": "report:read_history",
    }


def test_maintenance_work_context_uses_maintenance_audience_and_order_check(monkeypatch) -> None:
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        if url.endswith("tokens/exchange"):
            return response(200, {"access_token": "maintenance-token"})
        assert kwargs["headers"]["Authorization"] == "Bearer maintenance-token"
        return response(200, {"allowed": True, "property_id": str(uuid4())})

    monkeypatch.setattr(httpx, "post", post)
    actor, order_id, report_id = principal({"report:read_work_context"}), uuid4(), uuid4()
    assert MaintenanceClient(settings(), Tokens()).order_access(actor, order_id, report_id)["allowed"]
    assert calls[0][1]["target_audience"] == "maintenance-service"
    assert calls[1][1]["order_id"] == str(order_id)
    assert calls[1][1]["report_id"] == str(report_id)
