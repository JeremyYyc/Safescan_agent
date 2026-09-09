import os

os.environ.setdefault("PROPERTY_LEASING_DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-at-least-24-characters")

from fastapi.testclient import TestClient

from app.main import app


def test_p0_routes_and_lease_input_contract() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = schema["paths"]
    assert "/internal/v1/market-properties" in paths
    assert "/internal/v1/contact-requests" in paths
    assert "/internal/v1/applications/{application_id}/approve" in paths
    assert "/internal/v1/leases/{lease_id}/execute" in paths
    assert "/internal/v1/leases/{lease_id}/activate" in paths
    assert "/internal/v1/leases/{lease_id}/terminate" not in paths
    assert "/internal/v1/leases/{lease_id}/end" not in paths
    lease_create = schema["components"]["schemas"]["LeaseCreate"]
    assert "tenant_subject_id" not in lease_create["properties"]
    assert lease_create["additionalProperties"] is False


def test_public_market_endpoint_does_not_require_auth() -> None:
    operation = TestClient(app).get("/openapi.json").json()["paths"][
        "/internal/v1/market-properties"
    ]["get"]
    assert not operation.get("security")


def test_authentication_error_uses_unified_error_shape() -> None:
    response = TestClient(app, raise_server_exceptions=False).post(
        "/internal/v1/leases",
        headers={"Authorization": "Bearer invalid", "Idempotency-Key": "bad"},
        json={"tenant_subject_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert response.json()["error"]["retryable"] is False
