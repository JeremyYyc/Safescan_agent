#!/usr/bin/env python3
"""Validate fixtures, chronology, provenance and local files without third-party packages."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path

TABLES = ("housing_records", "media_assets", "housing_media", "execution_units", "simulated_residents", "simulated_tenancies",
          "simulated_inspections", "simulated_findings", "simulated_work_orders", "simulated_work_order_events", "execution_scenarios")
PROPERTY_FIELDS = ("address", "property_type", "bedrooms", "bathrooms", "rooms_count", "bed_count", "kitchen_count",
                   "living_room_count", "parking_spaces", "floor_area_sqm", "whole_apartment_bedrooms",
                   "whole_apartment_bathrooms", "whole_apartment_floor_area_sqm", "max_occupants", "furnished")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_tables(root):
    return {name: [json.loads(line) for line in (root / (name + ".jsonl")).read_text().split("\n") if line]
            for name in TABLES}


def validate_tables(tables, as_of=date(2026, 10, 31)):
    by = {}
    for name, rows in tables.items():
        if name == "housing_media":
            keys = [(r["housing_id"], r["media_id"]) for r in rows]
        else:
            keys = [r["id"] for r in rows]
            by[name] = {r["id"]: r for r in rows}
        require(len(keys) == len(set(keys)), "Duplicate IDs: " + name)
        if name not in ("housing_records", "media_assets", "housing_media"):
            require(all(r.get("is_synthetic") is True for r in rows), "Missing simulation label: " + name)
    units, leases = by["execution_units"], by["simulated_tenancies"]
    inspections, orders = by["simulated_inspections"], by["simulated_work_orders"]
    housing, media = by["housing_records"], by["media_assets"]
    for row in tables["housing_media"]:
        require(row["housing_id"] in housing and row["media_id"] in media, "Unknown housing/media link")
    per_unit = defaultdict(list)
    for row in units.values():
        require(row["housing_id"] in housing, "Unknown source housing")
        require(row["weekly_rent"] > 0 and row["currency"] == "AUD", "Invalid unit rent")
        require(row["physical_unit_number"] is None, "Invented physical unit number")
        require(all(mid in media for mid in row["marketing_media_ids"]), "Unknown marketing image")
        require(not row["inspection_evidence_media_ids"], "Marketing photo used as inspection evidence")
        require(row.get("property_fields_version") == 2, "Missing completed property version")
        for key in PROPERTY_FIELDS:
            require(key in row and row[key] is not None and row[key] != "", "Missing effective property field: " + key)
            require(row["property_profile"].get(key) == row[key], "Profile/top-level property mismatch: " + key)
            require(row["property_field_sources"][key]["origin"] in ("observed", "derived_from_source", "simulated"), "Missing field provenance")
        require(isinstance(row["furnished"], bool), "Invalid furnishing flag")
        for key in ("bedrooms", "rooms_count", "bed_count", "kitchen_count", "living_room_count", "parking_spaces", "max_occupants", "whole_apartment_bedrooms"):
            require(type(row[key]) is int and row[key] >= 0, "Invalid property count: " + key)
        require(row["bathrooms"] > 0 and row["floor_area_sqm"] > 0, "Invalid bathroom count or area")
        require(row["whole_apartment_bedrooms"] >= row["bedrooms"] and row["whole_apartment_bathrooms"] >= row["bathrooms"], "Whole-apartment / leased-room count mismatch")
        require(row["whole_apartment_floor_area_sqm"] >= row["floor_area_sqm"], "Whole-apartment / leased-room area mismatch")
        for key in ("bedrooms", "bathrooms"):
            observed = row["observed_layout"].get(key)
            require(observed is None or row["whole_apartment_" + key] == observed, "Known source count overwritten: " + key)
    for lease in leases.values():
        require(lease["unit_id"] in units and lease["resident_id"] in by["simulated_residents"], "Unknown unit/resident")
        start, end = date.fromisoformat(lease["starts_on"]), date.fromisoformat(lease["ends_on"])
        require(start <= end and lease["weekly_rent"] > 0, "Invalid tenancy values")
        unit = units[lease["unit_id"]]
        require(lease["occupants"] <= unit["max_occupants"], "Tenancy exceeds simulated occupancy capacity")
        require(lease["rent_basis"] == ("room_per_week" if unit["rental_scope"] == "private_room" else "property_per_week"), "Rental scope / rent basis mismatch")
        require(lease["signed_at"][:10] <= min(str(start), str(as_of)), "Tenancy signed in future")
        require((lease["status"] == "ended" and end < as_of) or
                (lease["status"] == "active" and start <= as_of <= end) or
                (lease["status"] == "executed" and start > as_of), "Tenancy status/date mismatch")
        per_unit[lease["unit_id"]].append(lease)
    for uid, rows in per_unit.items():
        rows.sort(key=lambda r: r["starts_on"])
        require(all(a["ends_on"] < b["starts_on"] for a, b in zip(rows, rows[1:])), "Overlapping tenancies: " + uid)
        active = sum(r["status"] == "active" for r in rows)
        reserved = sum(r["status"] == "executed" for r in rows)
        expected = units[uid]["scenario_status"]
        require((expected == "active" and active == 1 and reserved == 0) or
                (expected == "reserved" and active == 0 and reserved == 1) or
                (expected == "vacant" and active == 0 and reserved == 0), "Unit occupancy/lease mismatch")
    for resident in by["simulated_residents"].values():
        require(resident["email"].endswith("@example.invalid") and resident["phone"] is None, "Non-test contact information")
    for row in inspections.values():
        lease = leases[row["tenancy_id"]]
        require(row["unit_id"] == lease["unit_id"], "Inspection cross-unit tenancy")
        day = row["scheduled_at"][:10]
        require(lease["starts_on"] <= day <= lease["ends_on"], "Inspection outside tenancy")
        if row["status"] == "completed":
            require(row["completed_at"] and row["completed_at"][:10] <= str(as_of), "Future completed inspection")
        else:
            require(row["completed_at"] is None and day > str(as_of), "Invalid planned inspection")
        require(not row["evidence_media_ids"], "Fake inspection image evidence")
        for fid in row["finding_ids"]:
            require(fid in by["simulated_findings"] and by["simulated_findings"][fid]["inspection_id"] == row["id"], "Missing finding")
    for row in orders.values():
        lease = leases[row["tenancy_id"]]
        require(lease["unit_id"] == row["unit_id"], "Work order cross-unit tenancy")
        require(lease["resident_id"] == row["reported_by_resident_id"], "Work order wrong reporting resident")
        require(lease["starts_on"] <= row["reported_at"][:10] <= min(lease["ends_on"], str(as_of)), "Order outside occupancy")
        for field, status in (("completed_at", "completed"), ("cancelled_at", "cancelled")):
            require(bool(row[field]) == (row["status"] == status), "Work-order terminal timestamp mismatch")
            if row[field]:
                require(row["reported_at"] <= row[field] and row[field][:10] <= min(lease["ends_on"], str(as_of)), "Invalid repair completion date")
        if row["inspection_id"]:
            inspection = inspections[row["inspection_id"]]
            require(inspection["unit_id"] == row["unit_id"] and inspection["tenancy_id"] == row["tenancy_id"], "Work order wrong inspection")
        if row["finding_id"]:
            require(by["simulated_findings"][row["finding_id"]]["work_order_id"] == row["id"], "Order/finding mismatch")
        require(not row["evidence_media_ids"], "Fake defect image evidence")
        require(row["cost_aud"] >= 0 and (row["status"] == "completed" or row["cost_aud"] == 0), "Invalid actual cost")
    for row in by["simulated_findings"].values():
        inspection, order = inspections[row["inspection_id"]], orders[row["work_order_id"]]
        require(inspection["unit_id"] == row["unit_id"] == order["unit_id"], "Finding cross-unit link")
        require(inspection["tenancy_id"] == row["tenancy_id"] == order["tenancy_id"], "Finding cross-tenancy link")
        require(row["id"] in inspection["finding_ids"] and row["observed_at"] <= order["reported_at"], "Finding chronology mismatch")
    events = defaultdict(list)
    transitions = {None: {"open"}, "open": {"assigned", "cancelled"}, "assigned": {"in_progress"},
                   "in_progress": {"blocked", "completed"}}
    for event in tables["simulated_work_order_events"]:
        require(event["work_order_id"] in orders, "Unknown event order")
        events[event["work_order_id"]].append(event)
    for wid, row in orders.items():
        history = sorted(events[wid], key=lambda r: r["sequence_no"])
        require([e["sequence_no"] for e in history] == list(range(1, len(history) + 1)), "Non-contiguous event sequence")
        previous, when = None, row["reported_at"]
        for event in history:
            require(event["from_status"] == previous and event["to_status"] in transitions.get(previous, set()), "Invalid work-order transition")
            require(when <= event["occurred_at"] and event["occurred_at"][:10] <= str(as_of), "Event time disorder")
            previous, when = event["to_status"], event["occurred_at"]
        require(previous == row["status"], "Final event/order state mismatch")
        terminal = row["completed_at"] or row["cancelled_at"]
        require(not terminal or terminal == when, "Final event/order timestamp mismatch")
    for row in tables["execution_scenarios"]:
        uid = row["unit_id"]
        expected_leases = sorted(r["id"] for r in per_unit[uid])
        expected_orders = sorted(r["id"] for r in orders.values() if r["unit_id"] == uid and r["status"] not in ("completed", "cancelled"))
        require(sorted(row["expected_tenancy_ids"]) == expected_leases, "Scenario lease oracle mismatch")
        require(sorted(row["expected_open_work_order_ids"]) == expected_orders, "Scenario order oracle mismatch")
    return {"rows_checked": sum(len(v) for v in tables.values()), "units": len(units), "checks_passed": True}


def validate_files(root):
    objects = json.loads((root / "objects.json").read_text())
    keys = set()
    for row in objects:
        path = (root / row["local_path"]).resolve()
        require(path.is_relative_to(root.resolve()), "Unsafe object path")
        require(path.stat().st_size == row["byte_size"], "Image byte-size mismatch")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], "Image hash mismatch")
        key = row["bucket"], row["object_key"]
        require(key not in keys, "Duplicate object location")
        keys.add(key)
    media = [json.loads(line) for line in (root / "media_assets.jsonl").read_text().split("\n") if line]
    object_by_id = {o["sha256"]: o for o in objects}
    for row in media:
        require(row["id"] in object_by_id, "SQL media has no local object")
        obj = object_by_id[row["id"]]
        require((row["bucket"], row["object_key"], row["byte_size"]) == (obj["bucket"], obj["object_key"], obj["byte_size"]), "SQL/MinIO media mismatch")
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest.items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, "Manifest mismatch: " + name)
    return {"images_verified": len(objects), "manifest_files_verified": len(manifest)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    result = {**validate_tables(load_tables(args.root)), **validate_files(args.root)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
