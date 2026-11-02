#!/usr/bin/env python3
"""Read-only Gateway -> BFF -> Maintenance -> Property scope smoke for a seeded PM.

Only login and GET requests are issued. Credentials/tokens and customer details
are never printed. Use --observe before deploying to record a failing baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8080")
    parser.add_argument("--observe", action="store_true")
    args = parser.parse_args()
    opener = build_opener(ProxyHandler({}))

    def request(method, path, token=None, payload=None):
        headers = {"Accept": "application/json"}
        body = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        start = time.monotonic()
        try:
            response = opener.open(Request(args.base_url.rstrip("/") + path,
                                           data=body, headers=headers, method=method), timeout=20)
        except HTTPError as exc:
            response = exc
        data = json.loads(response.read())
        elapsed_ms = round((time.monotonic() - start) * 1000)
        summary = {"method": method, "path": path, "status": response.status,
                   "elapsed_ms": elapsed_ms}
        if response.status >= 400:
            error = data.get("error", {})
            summary.update(code=error.get("code"), details=error.get("details"))
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        return response.status, data.get("data", data)

    status, login = request("POST", "/api/v1/auth/login", payload={
        "email": os.getenv("PM_SMOKE_EMAIL", "NoahSafescan@outlook.com"),
        "password": os.getenv("PM_SMOKE_PASSWORD", "staffNoahMitchell123456"),
    })
    if status != 200:
        raise SystemExit("Login failed; see status above.")
    token = login["access_token"]
    status, bootstrap = request("GET", "/api/v1/staff/bootstrap", token)
    if status != 200:
        raise SystemExit("Staff bootstrap failed; see status above.")
    role = bootstrap["staff"]["role"]
    staff_id = bootstrap["staff"]["id"]
    properties = set()
    cursor = None
    for _ in range(0 if role == "maintainer" else 100):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        status, page = request("GET", "/api/v1/staff/properties?" + urlencode(params), token)
        if status != 200:
            raise SystemExit("Assigned properties failed; see status above.")
        properties.update(item["id"] for item in page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    else:
        if role != "maintainer":
            raise SystemExit("Property pagination did not terminate.")

    seen = set()
    cursor = None
    first_id = None
    for _ in range(300):
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        status, page = request("GET", "/api/v1/staff/maintenance-orders?" + urlencode(params), token)
        if status != 200:
            if args.observe:
                print(json.dumps({"baseline": "maintenance request failed", "status": status}))
                return
            raise SystemExit("Maintenance page failed; see status above.")
        for item in page["items"]:
            if role == "maintainer":
                assert item.get("assigned_staff", {}).get("id") == staff_id, "Unassigned maintenance order"
            else:
                assert item["property"]["id"] in properties, "Out-of-scope maintenance order"
            assert item["id"] not in seen, "Duplicate maintenance order across pages"
            seen.add(item["id"])
            first_id = first_id or item["id"]
        next_cursor = page.get("next_cursor")
        if not next_cursor:
            break
        assert next_cursor != cursor, "Maintenance cursor did not advance"
        cursor = next_cursor
    else:
        raise SystemExit("Maintenance pagination did not terminate.")
    if first_id:
        status, detail = request("GET", "/api/v1/staff/maintenance-orders/" + first_id, token)
        assert status == 200 and detail["id"] == first_id, "Maintenance detail failed"
    print(json.dumps({"result": "passed", "assigned_properties": len(properties),
                      "role": role, "visible_orders": len(seen), "detail_checked": bool(first_id)}))


if __name__ == "__main__":
    main()
