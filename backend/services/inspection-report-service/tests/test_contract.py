from fastapi.testclient import TestClient
import json
from pathlib import Path

from inspection_report_service.main import app


def test_p0_producer_routes_and_input_contract() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = schema["paths"]
    required = {
        "/internal/v1/properties/{property_id}/reports",
        "/internal/v1/reports",
        "/internal/v1/reports/{report_id}",
        "/internal/v1/reports/{report_id}/work-context",
        "/internal/v1/reports/{report_id}/files/videos",
        "/internal/v1/reports/{report_id}/jobs",
        "/internal/v1/report-jobs/{job_id}",
        "/internal/v1/report-jobs/{job_id}/events",
        "/internal/v1/report-jobs/{job_id}/cancel",
        "/internal/v1/files/{file_id}/content",
    }
    assert required <= paths.keys()
    create = schema["components"]["schemas"]["ReportCreate"]
    assert "property_id" not in create["properties"]
    assert "source_lease_id" not in create["properties"]
    assert create["additionalProperties"] is False


def test_report_creation_requires_idempotency_key() -> None:
    operation = TestClient(app).get("/openapi.json").json()["paths"][
        "/internal/v1/properties/{property_id}/reports"
    ]["post"]
    header = next(item for item in operation["parameters"] if item["name"] == "Idempotency-Key")
    assert header["required"] is True
    assert header["schema"]["format"] == "uuid"


def test_invalid_token_uses_unified_error_shape() -> None:
    response = TestClient(app, raise_server_exceptions=False).get(
        "/internal/v1/reports/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert response.json()["error"]["retryable"] is False


def test_checked_in_openapi_snapshot_matches_producer() -> None:
    snapshot = Path(__file__).resolve().parents[4] / "docs" / "backend" / "openapi" / "inspection-report-service.json"
    assert json.loads(snapshot.read_text(encoding="utf-8")) == app.openapi()
