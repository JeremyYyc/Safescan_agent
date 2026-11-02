#!/usr/bin/env python3
"""Compile an append-only, conflict-checked import into the service-owned tables.

No credentials or deployment settings are read. Apply the resulting SQL with
psql after Alembic upgrade head. Source UUIDs and references are stable.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from dataset_io import canonical_address, write_json
from safescan_common.cities import STAFF_CITIES, normalize_city


def literal(value, json_value=False):
    if value is None:
        return "NULL"
    if json_value:
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "\'" + str(value).replace("\'", "\'\'") + "\'"


def city_staff(prefix, city, key):
    candidates = sorted(code for code, value in STAFF_CITIES.items()
                        if code.startswith(prefix) and value == city)
    return candidates[int(hashlib.sha256(str(key).encode()).hexdigest()[:8], 16) % len(candidates)] if candidates else None
from validate_execution_dataset import load_tables, validate_tables

NAMESPACE = UUID("20101031-0a57-4f32-8dc9-777ca2610500")
PREFIX = "safescan-au-execution-20261031-v2"
PRESERVED_TABLES = (
    "identity_access.users",
    "identity_access.customer_profiles",
    "identity_access.staff",
    "property_leasing.buildings",
    "property_leasing.properties",
    "property_leasing.parties",
    "property_leasing.staff_building_scopes",
    "property_leasing.prospect_cases",
    "property_leasing.tenancy_applications",
    "property_leasing.leases",
    "property_leasing.lease_tenants",
    "property_leasing.lease_documents",
    "inspection_report.inspections",
    "inspection_report.inspection_findings",
    "maintenance.maintenance_orders",
    "maintenance.maintenance_events",
)


def public_id(kind, source):
    return str(uuid5(NAMESPACE, f"{kind}:{source}"))


STUDIO_COUNT_SOURCE = {
    "origin": "simulated",
    "evidence": "User-defined business convention: Studio counts as one room; original source snapshot retained",
}


def business_property_profile(source):
    profile = deepcopy(source)
    if profile["rental_scope"] == "studio":
        for field in ("bedrooms", "whole_apartment_bedrooms", "rooms_count"):
            profile[field] = 1
            profile["field_sources"][field] = dict(STUDIO_COUNT_SOURCE)
    return profile


def compile_import(root, output, *, preserve_existing=False):
    tables = load_tables(root)
    validate_tables(tables)
    units = tables["execution_units"]
    housing = {r["id"]: r for r in tables["housing_records"]}
    media = {r["id"]: r for r in tables["media_assets"]}
    residents = {r["id"]: r for r in tables["simulated_residents"]}
    leases = {r["id"]: r for r in tables["simulated_tenancies"]}
    events = defaultdict(list)
    for e in tables["simulated_work_order_events"]:
        events[e["work_order_id"]].append(e)
    buildings, property_rows, resident_rows, lease_rows = {}, [], [], []
    for index, u in enumerate(units):
        address_key = canonical_address(u["address"])
        bid = public_id("building", address_key)
        city = normalize_city(housing[u["housing_id"]].get("city"),
                              housing[u["housing_id"]].get("region"), u["address"])
        manager = city_staff("PM", city, address_key)
        consultant = city_staff("LC", city, u["id"])
        buildings.setdefault(
            bid,
            {
                "public_id": bid,
                "reference": "SIM-AU26-B-" + bid[:12],
                "name": housing[u["housing_id"]]["name"],
                "address": u["address"],
                "timezone": u["timezone"],
                "manager_code": manager,
                "city_id": city,
            },
        )
        attrs = {
            **business_property_profile(u["property_profile"]),
            "dataset": PREFIX,
            "source_id": u["id"],
            "source_url": u["source_url"],
            "room_number": u["simulated_unit_label"],
            "is_synthetic": True,
            "consultant": {
                "staff_code": consultant,
                "display_name": f"租赁顾问 {consultant}" if consultant else "待分配",
            },
            "marketing_media": [
                {k: media[mid][k] for k in ("id", "bucket", "object_key", "mime_type")}
                for mid in u["marketing_media_ids"]
            ],
        }
        pid = public_id("property", u["id"])
        property_rows.append(
            {
                "public_id": pid,
                "building_public_id": bid,
                "reference": u["reference"],
                "address": u["address"],
                "bedrooms": attrs["bedrooms"],
                "bathrooms": u["bathrooms"],
                "parking_spaces": u["parking_spaces"],
                "floor_area_sqm": u["floor_area_sqm"],
                "weekly_rent": u["weekly_rent"],
                "status": {
                    "active": "occupied",
                    "reserved": "under_offer",
                    "vacant": "marketing",
                }[u["scenario_status"]],
                "listing_visibility": "public"
                if u["scenario_status"] == "vacant"
                else "staff",
                "attributes": attrs,
                "display_image_urls": [
                    f"/api/v1/staff/properties/{pid}/images/{m['id']}"
                    for m in attrs["marketing_media"]
                ],
                "consultant_code": consultant,
                "manager_code": manager,
                "city_id": city,
            }
        )
    by_property = {u["reference"]: u for u in property_rows}
    for r in residents.values():
        lease = next(l for l in leases.values() if l["resident_id"] == r["id"])
        resident_rows.append(
            {
                **r,
                "public_id": public_id("party", r["id"]),
                "subject_id": public_id("customer", r["id"]),
                "customer_status": "former_tenant"
                if lease["status"] == "ended"
                else "tenant",
                "signed_at": lease["signed_at"],
                "ended_at": lease["ended_at"],
                "username": "sim_" + r["id"].lower().replace("-", "_"),
            }
        )
    by_resident = {r["id"]: r for r in resident_rows}
    for l in leases.values():
        signed = datetime.fromisoformat(l["signed_at"])
        terms = {
            "is_synthetic": True,
            "dataset": PREFIX,
            "source_id": l["id"],
            "source_terms": l,
        }
        lease_rows.append(
            {
                **l,
                "public_id": public_id("lease", l["id"]),
                "property_public_id": by_property[l["unit_id"]]["public_id"],
                "party_public_id": by_resident[l["resident_id"]]["public_id"],
                "subject_id": by_resident[l["resident_id"]]["subject_id"],
                "application_public_id": public_id("application", l["id"]),
                "case_public_id": public_id("case", l["id"]),
                "document_public_id": public_id("document", l["id"]),
                "consultant_code": by_property[l["unit_id"]]["consultant_code"],
                "company_signed_at": (signed + timedelta(minutes=5)).isoformat(),
                "executed_at": (signed + timedelta(minutes=10)).isoformat(),
                "terms": terms,
                "digest": hashlib.sha256(
                    json.dumps(terms, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
            }
        )
    inspection_rows = [
        {
            **i,
            "public_id": public_id("inspection", i["id"]),
            "property_public_id": public_id("property", i["unit_id"]),
            "lease_public_id": public_id("lease", i["tenancy_id"]),
            "manager_code": by_property[i["unit_id"]]["manager_code"],
        }
        for i in tables["simulated_inspections"]
    ]
    work_rows = [
        {
            **w,
            "public_id": public_id("work_order", w["id"]),
            "property_public_id": public_id("property", w["unit_id"]),
            "lease_public_id": public_id("lease", w["tenancy_id"]),
            "party_public_id": by_resident[w["reported_by_resident_id"]]["public_id"],
            "subject_id": by_resident[w["reported_by_resident_id"]]["subject_id"],
            "manager_code": by_property[w["unit_id"]]["manager_code"],
            "maintainer_code": (city_staff("MT", by_property[w["unit_id"]]["city_id"], w["unit_id"])
                                or (f"MT{int(hashlib.sha256(w['unit_id'].encode()).hexdigest()[:8], 16) % 3 + 1:03d}"
                                    if w["status"] in {"completed", "cancelled"} else None)),
            "event_count": len(events[w["id"]]),
        }
        for w in tables["simulated_work_orders"]
    ]
    event_rows = [
        {
            **e,
            "public_id": public_id("event", e["id"]),
            "order_public_id": public_id("work_order", e["work_order_id"]),
        }
        for e in tables["simulated_work_order_events"]
    ]
    # Keep simulated historical events, then record why an active order has no local worker.
    for work in work_rows:
        if work["maintainer_code"] is None and work["status"] not in {"open", "completed", "cancelled"}:
            work["event_count"] += 1
            event_rows.append({
                "public_id": public_id("city-pending-event", work["id"]),
                "order_public_id": work["public_id"], "work_order_id": work["id"],
                "sequence_no": work["event_count"], "from_status": work["status"],
                "to_status": "open", "message": "Awaiting a maintainer in the property city",
                "occurred_at": "2026-10-31T00:00:00Z", "reason": "no_same_city_maintainer",
            })
    work_by_id = {w["id"]: w for w in work_rows}
    for event in event_rows:
        if event["sequence_no"] != 1:
            continue
        work = work_by_id[event["work_order_id"]]
        prop = by_property[work["unit_id"]]
        building = buildings[prop["building_public_id"]]
        resident = by_resident[work["reported_by_resident_id"]]
        event["import_context"] = {
            "property": {
                "id": prop["public_id"],
                "reference": prop["reference"],
                "room": prop["attributes"]["room_number"],
                "building": {
                    "id": building["public_id"],
                    "name": building["name"],
                    "address": building["address"],
                },
            },
            "tenant": {
                "display_name": resident["display_name"],
                "email": resident["email"],
                "subject_id": resident["subject_id"],
            },
        }
    finding_rows = [
        {
            **f,
            "inspection_public_id": public_id("inspection", f["inspection_id"]),
            "work_order_public_id": public_id("work_order", f["work_order_id"]),
        }
        for f in tables["simulated_findings"]
    ]

    with output.open("w", encoding="utf-8") as out:
        out.write(
            "BEGIN;\nSET LOCAL standard_conforming_strings=on;\nSELECT pg_advisory_xact_lock(12608026,500);\n"
        )
        for table in PRESERVED_TABLES:
            out.write(
                f"CREATE TEMP TABLE preserve_{table.replace('.', '_')} ON COMMIT DROP AS SELECT id,to_jsonb(t) AS original FROM {table} t;\n"
            )
        out.write(
            "CREATE TEMP TABLE import_staff AS SELECT s.staff_code,s.display_name,s.public_id,s.city_id,r.code AS role,u.public_id AS subject_id FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id JOIN identity_access.roles r ON r.id=s.role_id WHERE s.employment_status='active' AND u.status='active' AND r.status='active';\n"
        )
        out.write(
            "DO $$ BEGIN IF (SELECT count(*) FROM import_staff WHERE staff_code IN ('MA001','PM001','PM002','PM003','PM004','LC001','LC002','LC003','LC004','MT001','MT002','MT003','LC005','PM005','MT004','MT005'))<>16 THEN RAISE EXCEPTION 'Required development staff not present; refusing import'; END IF; END $$;\n"
        )
        for name, rows in {
            "buildings": list(buildings.values()),
            "properties": property_rows,
            "residents": resident_rows,
            "leases": lease_rows,
            "inspections": inspection_rows,
            "orders": work_rows,
            "events": event_rows,
            "findings": finding_rows,
        }.items():
            out.write(f"CREATE TEMP TABLE src_{name}(p jsonb) ON COMMIT DROP;\n")
            for start in range(0, len(rows), 200):
                out.write(
                    f"INSERT INTO src_{name} VALUES "
                    + ",".join(
                        "(" + literal(r, True) + "::jsonb)"
                        for r in rows[start : start + 200]
                    )
                    + ";\n"
                )

        def append(table, select, keys=("public_id",)):
            stage = "expected_" + table.replace(".", "_")
            out.write(f"CREATE TEMP TABLE {stage} ON COMMIT DROP AS {select};\n")
            # Derive the exact column list from a bounded SELECT alias list below.
            columns = select.split("\nFROM", 1)[0].removeprefix("SELECT ")
            import re

            names = re.findall(r" AS ([a-z_]+)(?:,|$)", columns)
            if not names:
                raise ValueError("Explicit aliases required for " + table)
            join = " AND ".join(f"t.{k}=s.{k}" for k in keys)
            out.write(
                f"INSERT INTO {table} ({','.join(names)}) SELECT {','.join('s.' + n for n in names)} FROM {stage} s WHERE NOT EXISTS(SELECT 1 FROM {table} t WHERE {join}) ON CONFLICT DO NOTHING;\n"
            )
            # Manual sync may run after users/lifecycle workers have changed
            # operational state. Preserve every existing row and compare only
            # stable ownership/identity. Signed document terms stay immutable.
            immutable = {
                "identity_access.users": ("public_id", "email", "account_type"),
                "identity_access.customer_profiles": ("user_id",),
                "property_leasing.buildings": ("public_id", "reference", "address"),
                "property_leasing.properties": ("public_id", "reference", "building_id"),
                "property_leasing.parties": ("public_id", "subject_id"),
                "property_leasing.prospect_cases": ("public_id", "prospect_party_id", "property_id"),
                "property_leasing.tenancy_applications": ("public_id", "prospect_case_id", "property_id", "applicant_id"),
                "property_leasing.leases": ("public_id", "application_id", "property_id"),
                "property_leasing.lease_tenants": ("lease_id", "party_id"),
                "property_leasing.lease_documents": ("public_id", "lease_id", "version", "terms_payload", "terms_digest"),
                "inspection_report.inspections": ("public_id", "property_id", "source_lease_id"),
                "maintenance.maintenance_orders": ("public_id", "property_id", "lease_id", "reported_by_subject_id"),
                "maintenance.maintenance_events": ("public_id", "order_id", "sequence_no"),
            }
            compared = immutable.get(table, keys) if preserve_existing else names
            left, right = (
                ",".join("t." + c for c in compared),
                ",".join("s." + c for c in compared),
            )
            out.write(
                f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM {stage} s LEFT JOIN {table} t ON {join} WHERE t.{keys[0]} IS NULL OR ROW({left}) IS DISTINCT FROM ROW({right})) THEN RAISE EXCEPTION 'Import conflict in {table}; no existing rows overwritten'; END IF; END $$;\n"
            )

        append(
            "identity_access.users",
            """SELECT (p->>'subject_id')::uuid AS public_id,p->>'email' AS email,'customer'::text AS account_type,p->>'username' AS username,'active'::text AS status
FROM src_residents""",
        )
        append(
            "identity_access.customer_profiles",
            """SELECT u.id AS user_id,p->>'customer_status' AS customer_status,1 AS tenancy_version,(p->>'signed_at')::timestamptz AS tenant_since,(p->>'ended_at')::timestamptz AS former_tenant_at
FROM src_residents JOIN identity_access.users u ON u.public_id=(p->>'subject_id')::uuid""",
            ("user_id",),
        )
        append(
            "property_leasing.buildings",
            """SELECT (p->>'public_id')::uuid AS public_id,p->>'reference' AS reference,p->>'name' AS name,p->>'address' AS address,p->>'timezone' AS timezone,p->>'city_id' AS city_id,jsonb_build_object('dataset','safescan-au-execution-20261031-v2','is_synthetic',true) AS attributes
FROM src_buildings""",
        )
        # Reject a real existing residence at the same normalized address; a shared
        # student building can legitimately contain multiple synthetic rooms.
        out.write(
            "DO $$ BEGIN IF EXISTS(SELECT 1 FROM src_properties s JOIN property_leasing.properties t ON lower(regexp_replace(t.address,'[^a-zA-Z0-9]','','g'))=lower(regexp_replace(s.p->>'address','[^a-zA-Z0-9]','','g')) WHERE t.public_id<>(s.p->>'public_id')::uuid AND t.reference NOT LIKE 'SIM-AU26-%' AND s.p->'attributes'->>'rental_scope'='entire_property') THEN RAISE EXCEPTION 'Existing physical property address conflict'; END IF; END $$;\n"
        )
        append(
            "property_leasing.properties",
            """SELECT (p->>'public_id')::uuid AS public_id,b.id AS building_id,b.city_id AS city_id,p->>'reference' AS reference,p->>'address' AS address,(p->>'bedrooms')::int AS bedrooms,(p->>'bathrooms')::numeric AS bathrooms,(p->>'parking_spaces')::int AS parking_spaces,(p->>'floor_area_sqm')::numeric AS floor_area_sqm,(p->>'weekly_rent')::numeric AS weekly_rent,'AUD'::varchar(3) AS currency,p->>'status' AS status,p->>'listing_visibility' AS listing_visibility,p->'attributes' AS attributes,p->'display_image_urls' AS display_image_urls
FROM src_properties JOIN property_leasing.buildings b ON b.public_id=(p->>'building_public_id')::uuid""",
        )
        append(
            "property_leasing.staff_building_scopes",
            """SELECT s.public_id AS staff_id,b.id AS building_id,'primary_manager'::text AS scope_role,'2026-10-31T00:00:00Z'::timestamptz AS valid_from,a.subject_id AS assigned_by_subject_id
FROM src_buildings JOIN property_leasing.buildings b ON b.public_id=(p->>'public_id')::uuid JOIN import_staff s ON s.staff_code=p->>'manager_code' AND s.city_id=b.city_id AND s.role='property_manager' CROSS JOIN import_staff a WHERE a.staff_code='MA001'""",
            ("staff_id", "building_id", "scope_role", "valid_from"),
        )
        append(
            "property_leasing.parties",
            """SELECT (p->>'public_id')::uuid AS public_id,(p->>'subject_id')::uuid AS subject_id,'person'::text AS party_type,p->>'display_name' AS name,jsonb_build_object('email',p->>'email','is_synthetic',true,'dataset','safescan-au-execution-20261031-v2') AS contact,'active'::text AS status
FROM src_residents""",
        )
        append(
            "property_leasing.prospect_cases",
            """SELECT (p->>'case_public_id')::uuid AS public_id,r.id AS prospect_party_id,u.id AS property_id,s.public_id AS assigned_consultant_staff_id,'converted'::text AS stage,'closed'::text AS status,(p->>'signed_at')::timestamptz AS opened_at,(p->>'executed_at')::timestamptz AS closed_at
FROM src_leases JOIN property_leasing.parties r ON r.public_id=(p->>'party_public_id')::uuid JOIN property_leasing.properties u ON u.public_id=(p->>'property_public_id')::uuid LEFT JOIN import_staff s ON s.staff_code=p->>'consultant_code' AND s.city_id=u.city_id AND s.role='leasing_consultant'""",
        )
        append(
            "property_leasing.tenancy_applications",
            """SELECT (p->>'application_public_id')::uuid AS public_id,c.id AS prospect_case_id,u.id AS property_id,r.id AS applicant_id,(p->>'id')||'-APP' AS reference,'approved'::text AS status,(p->>'starts_on')::date AS desired_start_on,GREATEST(1,round(((p->>'ends_on')::date-(p->>'starts_on')::date+1)/30.0))::int AS term_months,(p->>'occupants')::int AS occupants,'模拟历史导入；无真实申请提交'::text AS note,(p->>'signed_at')::timestamptz AS submitted_at,(p->>'signed_at')::timestamptz AS decided_at
FROM src_leases JOIN property_leasing.prospect_cases c ON c.public_id=(p->>'case_public_id')::uuid JOIN property_leasing.properties u ON u.public_id=(p->>'property_public_id')::uuid JOIN property_leasing.parties r ON r.public_id=(p->>'party_public_id')::uuid""",
        )
        append(
            "property_leasing.leases",
            """SELECT (p->>'public_id')::uuid AS public_id,u.id AS property_id,a.id AS application_id,p->>'reference' AS reference,(p->>'starts_on')::date AS starts_on,(p->>'ends_on')::date AS ends_on,(p->>'weekly_rent')::numeric AS weekly_rent,'AUD'::varchar(3) AS currency,p->>'status' AS status,(p->>'signed_at')::timestamptz AS tenant_signed_at,(p->>'company_signed_at')::timestamptz AS company_signed_at,(p->>'executed_at')::timestamptz AS executed_at,(p->>'ended_at')::timestamptz AS ended_at
FROM src_leases JOIN property_leasing.properties u ON u.public_id=(p->>'property_public_id')::uuid JOIN property_leasing.tenancy_applications a ON a.public_id=(p->>'application_public_id')::uuid""",
        )
        append(
            "property_leasing.lease_tenants",
            """SELECT l.id AS lease_id,r.id AS party_id,'signed'::text AS signing_status,(p->>'signed_at')::timestamptz AS signed_at
FROM src_leases JOIN property_leasing.leases l ON l.public_id=(p->>'public_id')::uuid JOIN property_leasing.parties r ON r.public_id=(p->>'party_public_id')::uuid""",
            ("lease_id",),
        )
        new_cases_only = (" AND NOT EXISTS(SELECT 1 FROM preserve_property_leasing_prospect_cases original WHERE original.id=c.id)"
                          if preserve_existing else "")
        new_apps_only = (" AND NOT EXISTS(SELECT 1 FROM preserve_property_leasing_tenancy_applications original WHERE original.id=a.id)"
                         if preserve_existing else "")
        out.write(
            "UPDATE property_leasing.prospect_cases c SET converted_lease_id=l.id,converted_at=l.executed_at FROM src_leases s JOIN property_leasing.leases l ON l.public_id=(s.p->>'public_id')::uuid WHERE c.public_id=(s.p->>'case_public_id')::uuid AND c.converted_lease_id IS NULL" + new_cases_only + ";\n"
        )
        out.write(
            "UPDATE property_leasing.tenancy_applications a SET winning_lease_id=l.id FROM src_leases s JOIN property_leasing.leases l ON l.public_id=(s.p->>'public_id')::uuid WHERE a.public_id=(s.p->>'application_public_id')::uuid AND a.winning_lease_id IS NULL" + new_apps_only + ";\n"
        )
        append(
            "property_leasing.lease_documents",
            """SELECT (p->>'document_public_id')::uuid AS public_id,l.id AS lease_id,1 AS version,p->'terms' AS terms_payload,p->>'digest' AS terms_digest,'issued'::text AS status,s.subject_id AS created_by_subject_id
FROM src_leases JOIN property_leasing.leases l ON l.public_id=(p->>'public_id')::uuid CROSS JOIN import_staff s WHERE s.staff_code='MA001'""",
        )
        append(
            "property_leasing.customer_lease_slots",
            """SELECT (p->>'subject_id')::uuid AS customer_subject_id,l.id AS lease_id,l.status AS status,(p->>'executed_at')::timestamptz AS reserved_at
FROM src_leases JOIN property_leasing.leases l ON l.public_id=(p->>'public_id')::uuid WHERE l.status IN ('active','executed')""",
            ("customer_subject_id",),
        )
        append(
            "inspection_report.inspections",
            """SELECT (p->>'public_id')::uuid AS public_id,(p->>'property_public_id')::uuid AS property_id,(p->>'lease_public_id')::uuid AS source_lease_id,COALESCE(s.subject_id,a.subject_id) AS inspector_subject_id,p->>'kind' AS kind,(p->>'scheduled_at')::timestamptz AS inspected_at,p->>'status' AS status,p->>'summary' AS summary,p AS attributes
FROM src_inspections LEFT JOIN import_staff s ON s.staff_code=p->>'manager_code' CROSS JOIN import_staff a WHERE a.staff_code='MA001'""",
        )
        append(
            "maintenance.maintenance_orders",
            """SELECT (p->>'public_id')::uuid AS public_id,(p->>'property_public_id')::uuid AS property_id,(p->>'lease_public_id')::uuid AS lease_id,p->>'reference' AS reference,p->>'summary' AS summary,'【模拟数据】'||(p->>'description') AS description,p->>'priority' AS priority,CASE WHEN s.public_id IS NULL AND p->>'status' NOT IN ('completed','cancelled') THEN 'open' ELSE p->>'status' END AS status,(p->>'party_public_id')::uuid AS reported_by_party_id,(p->>'subject_id')::uuid AS reported_by_subject_id,CASE WHEN p->>'status' NOT IN ('open','cancelled') THEN s.public_id END AS assigned_staff_id,CASE WHEN s.public_id IS NOT NULL AND p->>'status' NOT IN ('open','cancelled') THEN COALESCE(a.public_id,admin.public_id) END AS assigned_by_staff_id,CASE WHEN s.public_id IS NOT NULL AND p->>'status' NOT IN ('open','cancelled') THEN (p->>'reported_at')::timestamptz END AS assigned_at,(p->>'completed_at')::timestamptz AS completed_at,(p->>'cancelled_at')::timestamptz AS cancelled_at,(p->>'event_count')::int AS version,(p->>'event_count')::bigint+1 AS next_event_sequence,(p->>'reported_at')::timestamptz AS created_at,COALESCE((p->>'completed_at')::timestamptz,(p->>'cancelled_at')::timestamptz,(p->>'reported_at')::timestamptz) AS updated_at
FROM src_orders JOIN property_leasing.properties u ON u.public_id=(p->>'property_public_id')::uuid LEFT JOIN import_staff s ON s.staff_code=p->>'maintainer_code' AND (s.city_id=u.city_id OR p->>'status' IN ('completed','cancelled')) AND s.role='maintainer' LEFT JOIN import_staff a ON a.staff_code=p->>'manager_code' AND a.city_id=u.city_id AND a.role='property_manager' CROSS JOIN import_staff admin WHERE admin.staff_code='MA001'""",
        )
        append(
            "maintenance.maintenance_events",
            """SELECT (p->>'public_id')::uuid AS public_id,o.id AS order_id,(p->>'sequence_no')::bigint AS sequence_no,'system'::text AS actor_type,'public'::text AS visibility,CASE WHEN (p->>'sequence_no')::int=1 THEN 'order.created' ELSE 'order.status_changed' END AS event_type,p->>'message' AS message,p->>'from_status' AS from_status,p->>'to_status' AS to_status,CASE WHEN (p->>'sequence_no')::int=1 THEN jsonb_set(p,'{import_context,assignee}',jsonb_build_object('id',s.public_id,'display_name',s.display_name,'staff_code',s.staff_code)) ELSE p END AS details,(p->>'occurred_at')::timestamptz AS created_at
FROM src_events JOIN maintenance.maintenance_orders o ON o.public_id=(p->>'order_public_id')::uuid LEFT JOIN import_staff s ON s.public_id=o.assigned_staff_id""",
        )
        append(
            "inspection_report.inspection_findings",
            """SELECT i.id AS inspection_id,p->>'location' AS area,p->>'description' AS description,p->>'severity' AS severity,p AS evidence
FROM src_findings JOIN inspection_report.inspections i ON i.public_id=(p->>'inspection_public_id')::uuid""",
            ("inspection_id", "area", "description"),
        )
        for table in PRESERVED_TABLES:
            out.write(
                f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM preserve_{table.replace('.', '_')} s LEFT JOIN {table} t ON t.id=s.id WHERE to_jsonb(t) IS DISTINCT FROM s.original) THEN RAISE EXCEPTION 'Pre-existing data changed in {table}; rolling back import'; END IF; END $$;\n"
            )
        out.write("COMMIT;\n")
    result = {
        "dataset": PREFIX,
        "property_count": len(units),
        "building_count": len(buildings),
        "resident_count": len(resident_rows),
        "lease_count": len(lease_rows),
        "inspection_count": len(inspection_rows),
        "finding_count": len(finding_rows),
        "work_order_count": len(work_rows),
        "event_count": len(event_rows),
        "id_mapping": {u["reference"]: u["public_id"] for u in property_rows},
        "sql_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    write_json(output.with_suffix(".manifest.json"), result)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "id_mapping"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preserve-existing", action="store_true",
                        help="Append missing rows while retaining existing operational state")
    args = parser.parse_args()
    compile_import(args.root, args.output, preserve_existing=args.preserve_existing)
