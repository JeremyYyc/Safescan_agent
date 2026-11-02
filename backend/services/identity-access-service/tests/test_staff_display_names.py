from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.dependencies import admin_service, current_principal
from app.domain.principal import Principal
from app.main import app
from app.mappers.user_mapper import UserMapper
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "account_type,scopes,status",
    [
        ("staff", {"maintenance:assign_assigned"}, 200),
        ("staff", {"work_order:read_assigned"}, 200),
        ("staff", {"maintenance:manage_all"}, 200),
        ("staff", {"property:read_market"}, 403),
        ("customer", {"maintenance:self:create"}, 403),
    ],
)
def test_display_names_requires_maintenance_staff_and_returns_minimal_shape(
    account_type, scopes, status
):
    service = Mock()
    staff_id = uuid4()
    service.staff_display_names.return_value = {
        "items": [{"id": str(staff_id), "display_name": "Daniel"}]
    }
    app.dependency_overrides[current_principal] = lambda: Principal(
        subject=str(uuid4()),
        account_type=account_type,
        scopes=frozenset(scopes),
        claims={},
    )
    app.dependency_overrides[admin_service] = lambda: service
    try:
        result = TestClient(app).post(
            "/api/v1/iam/staff/display-names:batch", json={"ids": [str(staff_id)]}
        )
        assert result.status_code == status
        if status == 200:
            assert result.json()["data"]["items"][0] == {
                "id": str(staff_id),
                "display_name": "Daniel",
            }
        else:
            service.staff_display_names.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_display_batch_schema_is_bounded_uuid_list():
    command = app.openapi()["components"]["schemas"]["StaffDisplayBatchRequest"]
    assert command["properties"]["ids"]["maxItems"] == 100
    assert command["properties"]["ids"]["items"]["format"] == "uuid"


def test_mapper_selects_only_display_projection_with_one_query():
    db = Mock()
    staff_id = uuid4()
    db.execute.return_value.mappings.return_value.all.return_value = [
        {"public_id": staff_id, "display_name": "Daniel"}
    ]
    result = UserMapper(db).staff_display_names([staff_id])
    assert result == [{"id": str(staff_id), "display_name": "Daniel"}]
    statement = db.execute.call_args.args[0]
    assert set(statement.selected_columns.keys()) == {"public_id", "display_name"}
    db.execute.assert_called_once()
