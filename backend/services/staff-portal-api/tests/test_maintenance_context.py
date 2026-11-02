from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from test_contract import handler, token

from app.auth import Principal
from app.cache import MemoryCache
from app.client import Clients, RequestContext
from app.errors import ApiError
from app.main import create_app
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


def test_property_detail_preserves_bounded_history_cursors_and_provenance():
    captured = []

    def transport(request):
        captured.append(request)
        path = request.url.path
        if path == "/internal/v1/properties/p-1":
            return httpx.Response(
                200,
                json={
                    "id": "p-1",
                    "attributes": {"field_sources": {"bedrooms": "source-export"}},
                },
            )
        if path == "/internal/v1/leases":
            assert request.url.params["limit"] == "100"
            assert "status" not in request.url.params
            return httpx.Response(
                200, json={"items": [], "next_cursor": "lease-cursor", "total": 101}
            )
        if path == "/internal/v1/maintenance-orders":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "open-1",
                            "status": "assigned",
                            "property": {"id": "p-1"},
                        },
                        {
                            "id": "done-1",
                            "status": "completed",
                            "property": {"id": "p-1"},
                        },
                    ],
                    "next_cursor": "order-cursor",
                    "total": 120,
                },
            )
        if path == "/internal/v1/projections/properties:batch":
            return httpx.Response(
                200, json={"items": [{"id": "p-1", "reference": "ROOM-1"}]}
            )
        if path == "/internal/v1/properties/p-1/inspections":
            return httpx.Response(
                200,
                json={"items": [{"id": "inspection-1", "findings": []}], "total": 1},
            )
        return handler(request)

    clients = Clients(transport=httpx.MockTransport(transport))
    with TestClient(create_app(clients=clients, cache=MemoryCache())) as browser:
        response = browser.get(
            "/api/v1/staff/properties/p-1",
            headers={"Authorization": "Bearer " + token()},
        )
    assert response.status_code == 200
    body = response.json()["data"]
    assert (
        body["property"]["attributes"]["field_sources"]["bedrooms"] == "source-export"
    )
    assert body["leases"]["next_cursor"] == "lease-cursor"
    assert body["maintenance"]["next_cursor"] == "order-cursor"
    assert body["open_maintenance"]["next_cursor"] == "order-cursor"
    assert [row["id"] for row in body["open_maintenance"]["items"]] == ["open-1"]
    assert body["inspections"]["items"][0]["id"] == "inspection-1"
    assert (
        len([call for call in captured if call.url.path.endswith("/properties:batch")])
        == 1
    )
