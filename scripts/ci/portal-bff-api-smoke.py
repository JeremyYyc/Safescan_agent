#!/usr/bin/env python3
"""Verify real browser token -> Identity exchange -> Property calls through both BFFs."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


@dataclass(frozen=True)
class Result:
    status: int
    body: dict


NO_PROXY_OPENER = build_opener(ProxyHandler({}))


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    token: str | None = None,
    idempotency_key: str | None = None,
) -> Result:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        response = NO_PROXY_OPENER.open(
            Request(f"{base_url}{path}", data=data, headers=headers, method=method),
            timeout=15,
        )
    except HTTPError as exc:
        response = exc
    raw = response.read()
    return Result(response.status, json.loads(raw) if raw else {})


def expect(result: Result, status: int) -> dict:
    assert result.status == status, (result.status, result.body)
    return result.body


def assert_property_page(payload: dict) -> None:
    data = payload["data"]
    assert data["items"], payload
    assert data["items"][0]["id"], payload


def assert_unimplemented_downstream_reached(result: Result) -> None:
    assert result.status == 404, (result.status, result.body)
    assert result.body["error"]["code"] == "resource_not_found", result.body


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: portal-bff-api-smoke.py BASE_URL")
    base_url = sys.argv[1].rstrip("/")

    staff_login = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": "EthanSafescan@outlook.com",
                "password": "staffEthanCarter123456",
            },
        ),
        200,
    )
    assert_property_page(
        expect(
            request(
                base_url,
                "GET",
                "/api/v1/staff/properties",
                token=staff_login["data"]["access_token"],
            ),
            200,
        )
    )

    manager_login = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": "CharlotteSafescan@outlook.com",
                "password": "staffCharlotteMorgan123456",
            },
        ),
        200,
    )
    manager_token = manager_login["data"]["access_token"]
    manager_orders = expect(request(
        base_url, "GET", "/api/v1/staff/maintenance-orders", token=manager_token
    ), 200)
    assert manager_orders["data"]["items"] == [], manager_orders
    report_validation = request(base_url, "GET", "/api/v1/staff/reports", token=manager_token)
    assert report_validation.status == 422, (report_validation.status, report_validation.body)

    tenant_email = f"portal-bff-smoke-{uuid4()}@example.com"
    tenant_password = "PortalBffSmoke123"
    tenant_registration = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/register",
            payload={
                "accepted_terms_version": "p0",
                "email": tenant_email,
                "password": tenant_password,
                "username": "Portal BFF Smoke",
            },
        ),
        201,
    )
    tenant_token = tenant_registration["data"]["access_token"]
    properties = expect(request(
        base_url, "GET", "/api/v1/tenant/properties", token=tenant_token
    ), 200)
    assert_property_page(properties)
    property_id = properties["data"]["items"][0]["id"]
    assert_unimplemented_downstream_reached(
        request(
            base_url,
            "GET",
            "/api/v1/tenant/maintenance-orders",
            token=tenant_token,
        )
    )
    assert_unimplemented_downstream_reached(
        request(
            base_url,
            "GET",
            f"/api/v1/tenant/reports/{uuid4()}",
            token=tenant_token,
        )
    )
    contact = expect(request(
        base_url, "POST", f"/api/v1/tenant/properties/{property_id}/contact",
        token=tenant_token, idempotency_key=str(uuid4()),
        payload={"message": "Maintenance P0 lease smoke", "client_message_id": str(uuid4())},
    ), 201)["data"]
    application = expect(request(
        base_url, "POST", "/api/v1/tenant/applications", token=tenant_token,
        idempotency_key=str(uuid4()), payload={
            "case_id": contact["id"], "property_id": property_id,
            "desired_start_on": date.today().isoformat(), "term_months": 12,
            "occupants": 1, "note": "Maintenance P0 smoke",
        },
    ), 201)["data"]
    application = expect(request(
        base_url, "POST", f"/api/v1/tenant/applications/{application['id']}/submit",
        token=tenant_token, idempotency_key=str(uuid4()),
        payload={"attestation": True, "version": application["version"]},
    ), 200)["data"]
    application = expect(request(
        base_url, "POST", f"/api/v1/staff/applications/{application['id']}/start-review",
        token=manager_token, payload={"version": application["version"]},
    ), 200)["data"]
    application = expect(request(
        base_url, "POST", f"/api/v1/staff/applications/{application['id']}/approve",
        token=manager_token, idempotency_key=str(uuid4()),
        payload={"version": application["version"], "decision_note": "CI approved"},
    ), 200)["data"]

    today = date.today()
    lease = expect(request(
        base_url, "POST", "/api/v1/staff/leases", token=manager_token,
        idempotency_key=str(uuid4()), payload={
            "application_id": application["id"], "starts_on": today.isoformat(),
            "ends_on": (today + timedelta(days=365)).isoformat(), "weekly_rent": "600.00",
            "currency": "AUD", "terms_payload": {"kind": "maintenance-ci-smoke"},
            "offer_expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    ), 201)["data"]
    document = lease["document"]
    lease = expect(request(
        base_url, "POST", f"/api/v1/staff/leases/{lease['id']}/send-for-signature",
        token=manager_token, idempotency_key=str(uuid4()),
        payload={"version": lease["version"], "lease_document_id": document["id"]},
    ), 200)["data"]
    lease = expect(request(
        base_url, "POST", f"/api/v1/tenant/leases/{lease['id']}/signature",
        token=tenant_token, idempotency_key=str(uuid4()), payload={
            "version": lease["version"], "lease_document_id": document["id"],
            "terms_digest": document["terms_digest"], "accepted": True,
        },
    ), 200)["data"]
    lease = expect(request(
        base_url, "POST", f"/api/v1/staff/leases/{lease['id']}/company-signature",
        token=manager_token, idempotency_key=str(uuid4()), payload={
            "version": lease["version"], "lease_document_id": document["id"],
            "terms_digest": document["terms_digest"], "accepted": True,
        },
    ), 200)["data"]
    lease = expect(request(
        base_url, "POST", f"/api/v1/staff/leases/{lease['id']}/execute",
        token=manager_token, idempotency_key=str(uuid4()), payload={"version": lease["version"]},
    ), 200)["data"]

    active_lease = None
    for _ in range(30):
        time.sleep(1)
        login = request(base_url, "POST", "/api/v1/auth/login",
                        payload={"email": tenant_email, "password": tenant_password})
        if login.status != 200:
            continue
        tenant_token = login.body["data"]["access_token"]
        leases = request(base_url, "GET", "/api/v1/tenant/leases", token=tenant_token)
        if leases.status == 200:
            active_lease = next((item for item in leases.body["data"]["items"]
                                 if item["id"] == lease["id"] and item["status"] == "active"), None)
        if active_lease:
            break
    assert active_lease, "real Property lifecycle/Identity tenancy propagation did not complete"

    create_key = str(uuid4())
    command = {"summary": "Kitchen sink is leaking", "description": "CI smoke",
               "priority": "high"}
    order = expect(request(
        base_url, "POST", "/api/v1/tenant/maintenance-orders", token=tenant_token,
        idempotency_key=create_key, payload=command,
    ), 201)["data"]
    replay = expect(request(
        base_url, "POST", "/api/v1/tenant/maintenance-orders", token=tenant_token,
        idempotency_key=create_key, payload=command,
    ), 201)["data"]
    assert replay["id"] == order["id"]
    assert order["lease_id"] == lease["id"] and order["property"]["id"] == property_id

    expect(request(
        base_url, "POST", f"/api/v1/tenant/maintenance-orders/{order['id']}/comments",
        token=tenant_token, idempotency_key=str(uuid4()),
        payload={"content": "Water is still flowing", "client_message_id": str(uuid4())},
    ), 201)
    tenant_order = expect(request(
        base_url, "GET", f"/api/v1/tenant/maintenance-orders/{order['id']}", token=tenant_token,
    ), 200)["data"]
    assert [event["sequence_no"] for event in tenant_order["timeline"]] == [1, 2]

    maintainers = expect(request(
        base_url, "GET", "/api/v1/iam/staff?role=maintainer&employment_status=active",
        token=manager_token,
    ), 200)["data"]
    assignee_id = next(item["id"] for item in maintainers
                       if item.get("display_name") == "Daniel Cooper")
    assigned = expect(request(
        base_url, "POST", f"/api/v1/staff/maintenance-orders/{order['id']}/assign",
        token=manager_token, idempotency_key=str(uuid4()),
        payload={"assigned_staff_id": assignee_id, "version": tenant_order["version"],
                 "note": "Real Identity maintainer projection"},
    ), 200)["data"]
    maintainer_login = expect(request(
        base_url, "POST", "/api/v1/auth/login",
        payload={"email": "DanielSafescan@outlook.com",
                 "password": "staffDanielCooper123456"},
    ), 200)["data"]
    maintainer_token = maintainer_login["access_token"]
    started = expect(request(
        base_url, "POST", f"/api/v1/staff/maintenance-orders/{order['id']}/transitions",
        token=maintainer_token, idempotency_key=str(uuid4()),
        payload={"to_status": "in_progress", "version": assigned["version"]},
    ), 200)["data"]
    completed = expect(request(
        base_url, "POST", f"/api/v1/staff/maintenance-orders/{order['id']}/transitions",
        token=maintainer_token, idempotency_key=str(uuid4()),
        payload={"to_status": "completed", "version": started["version"],
                 "note": "Repair verified"},
    ), 200)["data"]
    assert completed["status"] == "completed" and completed["completed_at"]
    assert len(completed["timeline"]) == 5
    print("Portal BFF, Identity, Property Leasing, and Maintenance real E2E smoke passed.")


if __name__ == "__main__":
    main()
