import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
import sqlalchemy as sa
from fastapi import Depends
from fastapi.testclient import TestClient

from inspection_report_service.config import get_settings
from inspection_report_service.database import get_db, get_engine, get_session_factory
from inspection_report_service.main import app
from inspection_report_service import routes
from inspection_report_service.service import ReportService


DB_URL = os.getenv("REPORT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="REPORT_TEST_DATABASE_URL is required")


class LeasingContractFixture:
    property_results = {}
    lease_results = {}

    def property_access(self, actor, property_id, action):
        return self.property_results.get(property_id, {"allowed": False})

    def lease_access(self, actor, lease_id, property_id, action):
        return self.lease_results.get(lease_id, {"allowed": False})


def token(account_type, scopes, *, customer_status=None, role=None, subject=None):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(subject or uuid4()), "account_type": account_type,
        "scopes": scopes, "iss": "safescan-identity", "aud": "inspection-report-service",
        "iat": now, "nbf": now - timedelta(seconds=1), "exp": now + timedelta(minutes=5),
        "jti": str(uuid4()),
    }
    if customer_status:
        claims["customer_status"] = customer_status
    if role:
        claims["role"] = role
        claims["staff_id"] = str(uuid4())
    return jwt.encode(claims, "report-test-secret-that-is-long-enough", algorithm="HS256")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("INSPECTION_REPORT_DATABASE_URL", DB_URL)
    monkeypatch.setenv("AUTH_SECRET", "report-test-secret-that-is-long-enough")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with sa.create_engine(DB_URL).begin() as connection:
        connection.execute(sa.text(
            "TRUNCATE inspection_report.report_idempotency_records,"
            "inspection_report.report_audit_events,inspection_report.report_job_events,"
            "inspection_report.report_job_steps,inspection_report.report_assets,"
            "inspection_report.report_analysis,inspection_report.report_jobs,"
            "inspection_report.files,inspection_report.reports CASCADE"
        ))
    leasing = LeasingContractFixture()
    leasing.property_results = {}
    leasing.lease_results = {}

    def override(db=Depends(get_db)):
        return ReportService(db, leasing, get_settings())

    app.dependency_overrides[routes.service] = override
    yield TestClient(app, raise_server_exceptions=False), leasing
    app.dependency_overrides.clear()


def headers(value, key=None):
    return {"Authorization": f"Bearer {value}", "Idempotency-Key": str(key or uuid4())}


def test_staff_api_creates_scoped_property_report(client) -> None:
    http, leasing = client
    property_id, lease_id = uuid4(), uuid4()
    leasing.property_results[property_id] = {"allowed": True, "active_lease_id": str(lease_id)}
    response = http.post(
        f"/internal/v1/properties/{property_id}/reports",
        headers=headers(token("staff", ["report:generate_assigned"], role="property_manager")),
        json={"title": "Scoped staff report"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["property_id"] == str(property_id)
    assert response.json()["source_lease_id"] == str(lease_id)


def test_tenant_api_binds_server_derived_active_lease_and_replays(client) -> None:
    http, leasing = client
    property_id, lease_id, subject, key = uuid4(), uuid4(), uuid4(), uuid4()
    leasing.property_results[property_id] = {"allowed": True, "active_lease_id": str(lease_id)}
    bearer = token("customer", ["report:self:create", "report:self:read"],
                   customer_status="tenant", subject=subject)
    first = http.post(f"/internal/v1/properties/{property_id}/reports",
                      headers=headers(bearer, key), json={})
    replay = http.post(f"/internal/v1/properties/{property_id}/reports",
                       headers=headers(bearer, key), json={})
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["source_lease_id"] == str(lease_id)


def test_out_of_scope_and_nonexistent_ids_have_identical_hidden_error(client) -> None:
    http, _ = client
    bearer = token("staff", ["report:read_assigned", "report:generate_assigned"],
                   role="property_manager")
    denied = http.post(f"/internal/v1/properties/{uuid4()}/reports",
                       headers=headers(bearer), json={})
    missing = http.get(f"/internal/v1/reports/{uuid4()}",
                       headers={"Authorization": f"Bearer {bearer}"})
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["error"]["code"] == missing.json()["error"]["code"] == "resource_not_found"
