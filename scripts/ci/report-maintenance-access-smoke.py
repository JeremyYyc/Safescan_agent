#!/usr/bin/env python3
"""Exercise Staff Portal -> Report -> Identity -> Maintenance delegation with real services."""

import os
from uuid import UUID, uuid4

import httpx
import jwt

from inspection_report_service.auth import Principal
from inspection_report_service.clients import MaintenanceClient
from inspection_report_service.config import get_settings


def payload(response: httpx.Response) -> dict:
    response.raise_for_status()
    body = response.json()
    return body.get("data", body)


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

    report_token = payload(httpx.post(
        f"{identity_url}/internal/v1/tokens/exchange",
        headers={"Authorization": f"Bearer {os.environ['STAFF_PORTAL_SERVICE_TOKEN']}"},
        json={
            "user_token": browser_token,
            "target_audience": "inspection-report-service",
            "requested_scopes": ["report:read_work_context", "work_order:read_assigned"],
        },
        timeout=5,
    ))["access_token"]
    claims = jwt.decode(report_token, options={"verify_signature": False})
    actor = claims.get("act") or {}
    principal = Principal(
        subject_id=UUID(actor.get("sub") or claims["sub"]),
        account_type=actor.get("account_type") or claims["account_type"],
        scopes=frozenset(claims.get("scopes", [])),
        token=report_token,
        staff_id=UUID(actor.get("staff_id") or claims["staff_id"]),
        role=actor.get("role") or claims.get("role"),
        customer_status=actor.get("customer_status") or claims.get("customer_status"),
    )
    result = MaintenanceClient(get_settings()).order_access(
        principal, UUID(order["id"]), uuid4()
    )
    assert result["allowed"] is True, result
    assert result["order_id"] == order["id"], result
    assert result["property_id"] == order["property"]["id"], result
    print("Real Report -> Identity -> Maintenance order-access smoke passed.")


if __name__ == "__main__":
    main()
