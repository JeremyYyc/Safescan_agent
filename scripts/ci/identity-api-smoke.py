#!/usr/bin/env python3
"""Exercise the Identity P0 browser-facing session flows through the gateway."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4


STAFF_ACCOUNTS = (
    ("EthanSafescan@outlook.com", "staffEthanCarter123456", "leasing_consultant"),
    ("OliviaSafescan@outlook.com", "staffOliviaBennett123456", "leasing_consultant"),
    ("LiamSafescan@outlook.com", "staffLiamFoster123456", "leasing_consultant"),
    ("SophiaSafescan@outlook.com", "staffSophiaReed123456", "leasing_consultant"),
    ("NoahSafescan@outlook.com", "staffNoahMitchell123456", "property_manager"),
    ("EmmaSafescan@outlook.com", "staffEmmaCollins123456", "property_manager"),
    ("JamesSafescan@outlook.com", "staffJamesParker123456", "property_manager"),
    ("AvaSafescan@outlook.com", "staffAvaRichardson123456", "property_manager"),
    ("DanielSafescan@outlook.com", "staffDanielCooper123456", "maintainer"),
    ("GraceSafescan@outlook.com", "staffGraceTurner123456", "maintainer"),
    ("HenrySafescan@outlook.com", "staffHenryWalker123456", "maintainer"),
    ("CharlotteSafescan@outlook.com", "staffCharlotteMorgan123456", "manager_admin"),
)


@dataclass(frozen=True)
class Result:
    status: int
    body: dict


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies))

    def cookie(self, name: str) -> str:
        for cookie in self.cookies:
            if cookie.name == name:
                return cookie.value
        raise AssertionError(f"response did not set {name}")

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> Result:
        request_headers = {"Accept": "application/json", **(headers or {})}
        data = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        request = Request(
            f"{self.base_url}{path}", data=data, headers=request_headers, method=method
        )
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as exc:
            response = exc
        raw = response.read()
        body = json.loads(raw) if raw else {}
        return Result(response.status, body)


def expect(result: Result, status: int) -> dict:
    assert result.status == status, (result.status, result.body)
    return result.body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def csrf(client: Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookie("safescan_csrf")}


def verify_customer_flow(base_url: str) -> None:
    client = Client(base_url)
    registered = expect(
        client.request(
            "POST",
            "/api/v1/auth/register",
            payload={
                "email": f"identity-smoke-{uuid4()}@example.com",
                "username": "Identity Smoke",
                "password": "IdentitySmoke123",
                "accepted_terms_version": "p0",
            },
        ),
        201,
    )["data"]
    assert "refresh_token" not in registered
    assert registered["portal"] == "tenant"
    assert registered["user"]["account_type"] == "customer"
    assert registered["user"]["customer"]["status"] == "prospect"

    access_token = registered["access_token"]
    me = expect(client.request("GET", "/api/v1/me", headers=bearer(access_token)), 200)["data"]
    assert me["user"]["id"] == registered["user"]["id"]
    assert me["scopes"] == registered["scopes"]

    previous_refresh = client.cookie("safescan_refresh")
    previous_csrf = client.cookie("safescan_csrf")
    refreshed = expect(
        client.request("POST", "/api/v1/auth/refresh", headers=csrf(client)), 200
    )["data"]
    assert "refresh_token" not in refreshed
    assert client.cookie("safescan_refresh") != previous_refresh

    replay = Client(base_url).request(
        "POST",
        "/api/v1/auth/refresh",
        headers={
            "Cookie": (
                f"safescan_refresh={previous_refresh}; safescan_csrf={previous_csrf}"
            ),
            "X-CSRF-Token": previous_csrf,
        },
    )
    assert replay.status == 401, (replay.status, replay.body)
    assert replay.body["error"]["code"] == "refresh_token_reused"


def verify_staff_logins_and_logout(base_url: str) -> None:
    manager: tuple[Client, str] | None = None
    for email, password, expected_role in STAFF_ACCOUNTS:
        client = Client(base_url)
        logged_in = expect(
            client.request(
                "POST", "/api/v1/auth/login", payload={"email": email, "password": password}
            ),
            200,
        )["data"]
        assert "refresh_token" not in logged_in
        assert logged_in["portal"] == "staff"
        assert logged_in["user"]["account_type"] == "staff"
        assert logged_in["user"]["staff"]["role"]["code"] == expected_role
        if expected_role == "manager_admin":
            assert "iam:staff:read" in logged_in["scopes"]
            manager = (client, logged_in["access_token"])

    assert manager is not None
    client, access_token = manager
    expect(
        client.request(
            "POST",
            "/api/v1/auth/logout",
            headers={**csrf(client), **bearer(access_token)},
        ),
        204,
    )
    stale = client.request("GET", "/api/v1/me", headers=bearer(access_token))
    assert stale.status == 401, (stale.status, stale.body)
    assert stale.body["error"]["code"] == "session_inactive"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: identity-api-smoke.py BASE_URL")
    verify_customer_flow(sys.argv[1])
    verify_staff_logins_and_logout(sys.argv[1])
    print("Identity P0 API smoke test passed.")


if __name__ == "__main__":
    main()
