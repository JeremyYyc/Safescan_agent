import os

os.environ.setdefault(
    "MAINTENANCE_DATABASE_URL", "postgresql+psycopg://x:x@localhost/x"
)
os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-at-least-24-characters")

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.api_contract


def test_p0_routes_are_exported_and_future_routes_are_disabled():
    schema = TestClient(app).get("/openapi.json").json()
    paths = schema["paths"]
    expected = {
        "/internal/v1/maintenance-orders",
        "/internal/v1/maintenance-orders/{order_id}",
        "/internal/v1/maintenance-orders/{order_id}/assignments",
        "/internal/v1/maintenance-orders/{order_id}/transitions",
        "/internal/v1/maintenance-orders/{order_id}/comments",
        "/internal/v1/maintenance-orders/{order_id}/events",
        "/internal/v1/maintenance-orders/{order_id}/work-context",
        "/internal/v1/projections/orders:batch",
        "/internal/v1/authorizations/order-access:check",
        "/internal/v1/privacy/subject-deletions:check",
        "/internal/v1/privacy/subject-deletions/{request_id}",
    }
    assert expected.issubset(paths)
    assert not any(
        "maintenance-drafts" in path or "approval-requests" in path for path in paths
    )


def test_create_schema_forbids_identity_fields_and_requires_idempotency():
    schema = TestClient(app).get("/openapi.json").json()
    create = schema["components"]["schemas"]["OrderCreate"]
    assert create["additionalProperties"] is False
    assert not {"subject_id", "staff_id", "role", "approved"} & set(
        create["properties"]
    )
    operation = schema["paths"]["/internal/v1/maintenance-orders"]["post"]
    header = next(
        item for item in operation["parameters"] if item["name"] == "Idempotency-Key"
    )
    assert header["required"] is True


def test_report_order_access_contract_is_strict_and_complete():
    schema = TestClient(app).get("/openapi.json").json()
    command = schema["components"]["schemas"]["OrderAccessCheck"]
    assert command["additionalProperties"] is False
    assert set(command["required"]) == {"subject_id", "order_id", "action", "report_id"}
    assert command["properties"]["action"]["const"] == "report:read_work_context"


def test_private_route_authentication_has_unified_shape():
    response = TestClient(app, raise_server_exceptions=False).get(
        "/internal/v1/maintenance-orders/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    assert response.json()["error"]["details"] == {}


def test_health_routes_are_public():
    schema = TestClient(app).get("/openapi.json").json()
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
