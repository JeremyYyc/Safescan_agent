#!/usr/bin/env python3
"""Exercise Staff Portal -> Report -> Identity -> Maintenance delegation with real services."""

import os
import base64
from uuid import UUID, uuid4

import httpx
import jwt

from inspection_report_service.auth import Principal
from inspection_report_service.clients import MaintenanceClient, PropertyLeasingClient
from inspection_report_service.config import get_settings


def payload(response: httpx.Response) -> dict:
    response.raise_for_status()
    body = response.json()
    return body.get("data", body)


def principal(token: str) -> Principal:
    claims = jwt.decode(token, options={"verify_signature": False})
    actor = claims.get("act") or {}
    return Principal(
        subject_id=UUID(actor.get("sub") or claims["sub"]),
        account_type=actor.get("account_type") or claims["account_type"],
        scopes=frozenset(claims.get("scopes", [])),
        token=token,
        staff_id=UUID(actor.get("staff_id") or claims["staff_id"]),
        role=actor.get("role") or claims.get("role"),
        customer_status=actor.get("customer_status") or claims.get("customer_status"),
    )


def main() -> None:
    identity_url = os.getenv("IDENTITY_BASE_URL", "http://identity-access-service:8001")
    portal_url = "http://staff-portal-api:8006"
    browser_token = payload(httpx.post(
        f"{identity_url}/api/v1/auth/login",
        json={"email": "DanielSafescan@outlook.com",
              "password": "staffDanielCooper123456"},
        timeout=5,
    ))["access_token"]
    orders = payload(httpx.get(
        f"{portal_url}/api/v1/staff/maintenance-orders",
        headers={"Authorization": f"Bearer {browser_token}"}, timeout=5,
    ))["items"]
    order = next(item for item in orders if item.get("assigned_staff"))

    encoded = base64.b64encode(
        f"staff-portal:{os.environ['STAFF_PORTAL_IDENTITY_CLIENT_SECRET']}".encode()
    ).decode()
    staff_service_token = payload(httpx.post(
        f"{identity_url}/internal/v1/service-tokens",
        headers={"Authorization": f"Basic {encoded}"},
        json={"requested_scopes": [
            "identity:token_exchange", "report:read_all", "report:read_work_context",
            "work_order:read_assigned",
        ]},
        timeout=5,
    ))["access_token"]

    report_token = payload(httpx.post(
        f"{identity_url}/internal/v1/tokens/exchange",
        headers={"Authorization": f"Bearer {staff_service_token}"},
        json={
            "user_token": browser_token,
            "target_audience": "inspection-report-service",
            "requested_scopes": ["report:read_work_context", "work_order:read_assigned"],
        },
        timeout=5,
    ))["access_token"]
    report_actor = principal(report_token)
    result = MaintenanceClient(get_settings()).order_access(
        report_actor, UUID(order["id"]), uuid4()
    )
    assert result["allowed"] is True, result
    assert result["order_id"] == order["id"], result
    assert result["property_id"] == order["property"]["id"], result

    manager_browser_token = payload(httpx.post(
        f"{identity_url}/api/v1/auth/login",
        json={"email": "CharlotteSafescan@outlook.com",
              "password": "staffCharlotteMorgan123456"},
        timeout=5,
    ))["access_token"]
    properties = payload(httpx.get(
        f"{portal_url}/api/v1/staff/properties",
        headers={"Authorization": f"Bearer {manager_browser_token}"}, timeout=5,
    ))["items"]
    property_id = UUID(properties[0]["id"])
    manager_report_token = payload(httpx.post(
        f"{identity_url}/internal/v1/tokens/exchange",
        headers={"Authorization": f"Bearer {staff_service_token}"},
        json={
            "user_token": manager_browser_token,
            "target_audience": "inspection-report-service",
            "requested_scopes": ["report:read_all"],
        },
        timeout=5,
    ))["access_token"]
    property_result = PropertyLeasingClient(get_settings()).property_access(
        principal(manager_report_token), property_id, "report:read"
    )
    assert property_result["allowed"] is True, property_result
    assert property_result["property_id"] == str(property_id), property_result
    assert get_settings().identity_client_secret.get_secret_value()
    print("Real Report -> Identity -> Maintenance/Property delegation smoke passed.")


if __name__ == "__main__":
    main()
