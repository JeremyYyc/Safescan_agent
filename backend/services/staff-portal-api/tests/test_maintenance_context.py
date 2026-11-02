from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.auth import Principal
from app.cache import MemoryCache
from app.client import RequestContext
from app.errors import ApiError
from app.models import Role
from app.service import PortalService


def service():
    return PortalService(
        SimpleNamespace(
            leasing=SimpleNamespace(request=AsyncMock()),
            identity=SimpleNamespace(request=AsyncMock()),
        ),
        MemoryCache(),
    )


def actor():
    return Principal(
        "subject", Role.PROPERTY_MANAGER, frozenset(), (), 1, 1, "token", {}
    )


@pytest.mark.asyncio
async def test_context_batches_only_current_page_and_does_not_mutate_cached_rows():
    portal = service()
    page = {
        "items": [
            {
                "id": f"order-{i}",
                "property": {"id": f"p-{i % 2}"},
                "assigned_staff": {"id": "staff-1"},
            }
            for i in range(50)
        ],
        "next_cursor": "next-page",
        "total": 500,
    }
    original = deepcopy(page)
    portal.clients.leasing.request.return_value = {
        "items": [
            {
                "id": "p-0",
                "reference": "ROOM-1",
                "address": "10 Harbour Road",
                "attributes": {"room_number": "101"},
                "building": {"name": "Harbour House"},
            },
        ]
    }
    portal.clients.identity.request.return_value = {
        "items": [
            {
                "id": "staff-1",
                "display_name": "Daniel Cooper",
                "email": "must-not-be-copied",
            },
        ]
    }
    result, partial = await portal.enrich_maintenance(
        actor(), RequestContext("cid", None, None), page
    )
    assert result["next_cursor"] == "next-page" and result["total"] == 500
    assert len(result["items"]) == 50 and partial == []
    assert result["items"][0]["property"]["building"]["name"] == "Harbour House"
    assert result["items"][1]["property"] == {"id": "p-1"}
    assert result["items"][0]["assigned_staff"] == {
        "id": "staff-1",
        "display_name": "Daniel Cooper",
    }
    assert page == original
    portal.clients.leasing.request.assert_awaited_once()
    assert portal.clients.leasing.request.call_args.kwargs["json"] == {
        "ids": ["p-0", "p-1"]
    }
    portal.clients.identity.request.assert_awaited_once()
    assert portal.clients.identity.request.call_args.kwargs["json"] == {
        "ids": ["staff-1"]
    }


@pytest.mark.asyncio
async def test_context_failure_preserves_orders_and_reports_partial_error():
    portal = service()
    page = {
        "items": [{"id": "order", "property": {"id": "p"}, "assigned_staff": None}],
        "next_cursor": "next",
    }
    portal.clients.leasing.request.side_effect = ApiError(
        504, "dependency_timeout", "timed out", retryable=True
    )
    result, partial = await portal.enrich_maintenance(
        actor(), RequestContext("cid", None, None), page
    )
    assert result == page
    assert partial == [
        {
            "component": "maintenance_properties",
            "code": "dependency_timeout",
            "retryable": True,
        }
    ]
    portal.clients.identity.request.assert_not_called()


@pytest.mark.asyncio
async def test_empty_page_does_not_call_projection_services():
    portal = service()
    result, partial = await portal.enrich_maintenance(
        actor(), RequestContext("cid", None, None), {"items": []}
    )
    assert result == {"items": []} and partial == []
    portal.clients.leasing.request.assert_not_called()
    portal.clients.identity.request.assert_not_called()
