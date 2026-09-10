#!/usr/bin/env python3
"""Verify real browser token -> Identity exchange -> Property calls through both BFFs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
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
) -> Result:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
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


def assert_skeleton_downstream_reached(result: Result) -> None:
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
    assert_skeleton_downstream_reached(
        request(
            base_url,
            "GET",
            "/api/v1/staff/maintenance-orders",
            token=manager_token,
        )
    )
    assert_skeleton_downstream_reached(
        request(base_url, "GET", "/api/v1/staff/reports", token=manager_token)
    )

    tenant_registration = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/register",
            payload={
                "accepted_terms_version": "p0",
                "email": f"portal-bff-smoke-{uuid4()}@example.com",
                "password": "PortalBffSmoke123",
                "username": "Portal BFF Smoke",
            },
        ),
        201,
    )
    tenant_token = tenant_registration["data"]["access_token"]
    assert_property_page(
        expect(
            request(
                base_url,
                "GET",
                "/api/v1/tenant/properties",
                token=tenant_token,
            ),
            200,
        )
    )
    assert_skeleton_downstream_reached(
        request(
            base_url,
            "GET",
            "/api/v1/tenant/maintenance-orders",
            token=tenant_token,
        )
    )
    assert_skeleton_downstream_reached(
        request(
            base_url,
            "GET",
            "/api/v1/tenant/reports/missing-report",
            token=tenant_token,
        )
    )
    print("Portal BFF real token exchange and downstream call smoke test passed.")


if __name__ == "__main__":
    main()
