#!/usr/bin/env python3
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from integrate_execution_dataset import public_id

parser = argparse.ArgumentParser(
    description="Read-only end-to-end verification of the 500 imported property histories"
)
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--base-url", default="http://localhost:8080")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--existing-properties", type=int, default=8)
args = parser.parse_args()
root = args.root
base = args.base_url.rstrip("/")
email = os.environ["SAFESCAN_VERIFY_EMAIL"]
password = os.environ["SAFESCAN_VERIFY_PASSWORD"]


def req(path, token=None, data=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        urllib.request.Request(
            base + path,
            headers=h,
            data=json.dumps(data).encode() if data is not None else None,
        ),
        timeout=30,
    )
    raw = r.read()
    return json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw


login = req(
    "/api/v1/auth/login",
    data={"email": email, "password": password, "remember_me": False},
)
token = login["data"]["access_token"]


def pages(path):
    rows = []
    cursor = None
    seen = set()
    while True:
        from urllib.parse import urlencode

        p = req(
            path
            + "?"
            + urlencode({"limit": 100, **({"cursor": cursor} if cursor else {})}),
            token,
        )["data"]
        rows += p["items"]
        cursor = p.get("next_cursor")
        if not cursor:
            return rows
        assert cursor not in seen
        seen.add(cursor)


props = pages("/api/v1/staff/properties")
sim = [p for p in props if p["reference"].startswith("SIM-AU26-")]
assert len(props) == 500 + args.existing_properties and len(sim) == 500
expect = {name: defaultdict(set) for name in ("leases", "inspections", "maintenance")}
for name, filename, kind in [
    ("leases", "simulated_tenancies", "lease"),
    ("inspections", "simulated_inspections", "inspection"),
    ("maintenance", "simulated_work_orders", "work_order"),
]:
    for line in (root / (filename + ".jsonl")).read_text().splitlines():
        r = json.loads(line)
        expect[name][public_id("property", r["unit_id"])].add(public_id(kind, r["id"]))


def check(p):
    r = req("/api/v1/staff/properties/" + p["id"], token)
    assert not r.get("meta", {}).get("partial_errors"), (p["reference"], r.get("meta"))
    d = r["data"]
    prop = d["property"]
    if prop["attributes"].get("rental_scope") == "studio":
        assert prop["bedrooms"] == 1
        assert all(prop["attributes"][field] == 1 for field in (
            "bedrooms", "whole_apartment_bedrooms", "rooms_count"
        ))
    for k in expect:
        ids = {x["id"] for x in d[k]["items"]}
        assert ids == expect[k][p["id"]], (
            p["reference"],
            k,
            len(ids),
            len(expect[k][p["id"]]),
        )
    return {k: len(d[k]["items"]) for k in expect}


started = time.monotonic()
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(check, sim))
first = req("/api/v1/staff/properties/" + sim[0]["id"], token)["data"]
image = first["property"]["display_image_urls"][0]
assert len(req(image, token)) > 100
order = first["maintenance"]["items"][0]
timeline = req("/api/v1/staff/maintenance-orders/" + order["id"], token)["data"][
    "timeline"
]
assert len(timeline) > 0
public = req("/api/v1/tenant/properties?limit=100")["data"]["items"]
public_sim = [p for p in public if p["reference"].startswith("SIM-AU26-")]
assert len(public_sim) == 81
p = public_sim[0]
assert len(req(p["display_image_urls"][0].replace("/staff/", "/tenant/"))) > 100
try:
    req(image)
except urllib.error.HTTPError as e:
    assert e.code == 401
else:
    raise AssertionError("Staff image accessible without authorization")
private = next(p for p in sim if p["listing_visibility"] == "staff")
try:
    req("/api/v1/tenant/properties/" + private["id"])
except urllib.error.HTTPError as e:
    assert e.code == 404
else:
    raise AssertionError("Private property publicly accessible")
summary = {
    "verified_at": datetime.now(UTC).isoformat(),
    "staff_properties": len(props),
    "imported_properties": len(sim),
    "all_500_detail_pages_verified": True,
    "studio_one_room_convention_verified": True,
    "detail_totals": {k: sum(r[k] for r in results) for k in expect},
    "public_imported_properties": len(public_sim),
    "staff_and_public_images_verified": True,
    "work_order_timeline_verified": True,
    "unauthorized_staff_image_denied": True,
    "private_property_hidden_from_market": True,
    "elapsed_seconds": round(time.monotonic() - started, 2),
}
args.output.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
