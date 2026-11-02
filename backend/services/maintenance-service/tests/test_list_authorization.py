from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.core.pagination import decode_cursor
from app.domain.principal import Principal
from app.models.tables import MaintenanceOrder
from app.services.maintenance import MaintenanceService

pytestmark = pytest.mark.unit


def manager():
    return Principal(
        subject_id=uuid4(),
        account_type="staff",
        staff_id=uuid4(),
        scopes=frozenset({"maintenance:assign_assigned"}),
        claims={},
    )


def orders(count):
    now = datetime.now(UTC)
    return [
        MaintenanceOrder(
            id=index + 1,
            public_id=uuid4(),
            property_id=uuid4(),
            reference=f"MO-{index}",
            summary="Repair",
            status="open",
            priority="normal",
            version=1,
            created_at=now - timedelta(seconds=index),
        )
        for index in range(count)
    ]


def test_manager_page_authorizes_once_and_cursor_tracks_last_scanned_order():
    rows = orders(201)
    db, dependencies = Mock(), Mock()
    db.scalars.side_effect = [rows, []]
    dependencies.property_access_batch.return_value = {
        row.property_id: index % 2 == 0 for index, row in enumerate(rows)
    }
    result = MaintenanceService(db, dependencies, Mock()).list(
        manager(), None, None, None, None, None, 50
    )
    assert [item["id"] for item in result["items"]] == [
        str(row.public_id) for row in rows[:99:2]
    ]
    assert decode_cursor(result["next_cursor"]) == (rows[98].created_at, rows[98].id)
    dependencies.property_access_batch.assert_called_once()
    dependencies.property_access.assert_not_called()


def test_manager_scan_without_visible_orders_still_advances_cursor():
    rows = orders(201)
    db, dependencies = Mock(), Mock()
    db.scalars.side_effect = [rows, []]
    dependencies.property_access_batch.return_value = {
        row.property_id: False for row in rows
    }
    result = MaintenanceService(db, dependencies, Mock()).list(
        manager(), None, None, None, None, None, 50
    )
    assert result["items"] == []
    assert decode_cursor(result["next_cursor"]) == (rows[-1].created_at, rows[-1].id)


def test_manager_batch_filters_invisible_orders_with_one_authorization():
    rows = orders(100)
    db, dependencies = Mock(), Mock()
    db.scalars.return_value = rows
    dependencies.property_access_batch.return_value = {
        row.property_id: index % 2 == 0 for index, row in enumerate(rows)
    }
    result = MaintenanceService(db, dependencies, Mock()).batch(
        manager(), [row.public_id for row in reversed(rows)]
    )
    assert [item["id"] for item in result] == [
        str(row.public_id) for row in reversed(rows[::2])
    ]
    dependencies.property_access_batch.assert_called_once()
    dependencies.property_access.assert_not_called()
