#!/usr/bin/env python3
"""Reconcile existing city ownership in one transaction; default is a rollback-only preview.

DATABASE_URL is read from the environment. --dataset must point at the authoritative
execution export containing execution_units.jsonl and housing_records.jsonl.
Existing non-demo staff cities are retained. Unknown locations remain unassigned.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from safescan_common.cities import STAFF_CITIES, same_city, normalize_city


def source_cities(root):
    def rows(name):
        return [json.loads(line) for line in (root / f"{name}.jsonl").read_text().split("\n") if line]
    housing = {r["id"]: r for r in rows("housing_records")}
    return {u["reference"]: normalize_city(housing[u["housing_id"]].get("city"),
                                       housing[u["housing_id"]].get("region"), u["address"])
            for u in rows("execution_units")}


def pick_staff(pool, role, city, key):
    candidates = sorted((r for r in pool if r["role"] == role and same_city(r["city_id"], city)
                         and r["employment_status"] == "active" and r["status"] == "active"
                         and r["role_status"] == "active"), key=lambda r: r["staff_code"])
    if not candidates:
        return None
    return candidates[int(hashlib.sha256(str(key).encode()).hexdigest()[:8], 16) % len(candidates)]


def reconcile(connection, mapping, *, staff_cities=None):
    c = connection
    c.execute(sa.text("SELECT pg_advisory_xact_lock(12608026,500)"))
    # Ordinary domain writes cannot race the one-time ownership switch.
    c.execute(sa.text("""LOCK TABLE identity_access.staff, property_leasing.buildings,
        property_leasing.properties, property_leasing.staff_building_scopes,
        property_leasing.staff_property_scopes, property_leasing.prospect_cases,
        property_leasing.prospect_contact_threads, maintenance.maintenance_orders
        IN SHARE ROW EXCLUSIVE MODE"""))
    now, correlation = c.scalar(sa.text("SELECT CURRENT_TIMESTAMP")), uuid4()
    counts = Counter()
    def rows(sql, **params):
        return [dict(r) for r in c.execute(sa.text(sql), params).mappings()]
    def run(sql, **params):
        return c.execute(sa.text(sql), params)
    def audit(kind, details, user_id=None):
        run("""INSERT INTO identity_access.auth_events
            (user_id,event_type,occurred_at,correlation_id,details_redacted)
            VALUES (:uid,:kind,:now,:cid,CAST(:details AS jsonb))""",
            uid=user_id, kind=kind, now=now, cid=correlation,
            details=json.dumps(details, default=str))
    valid_cities = {r["id"] for r in rows("SELECT id FROM identity_access.cities")}
    if (set(mapping.values()) - {None}) - valid_cities:
        raise ValueError("Dataset contains an unsupported city")
    pool = rows("""SELECT s.*, r.code AS role,r.status AS role_status,u.status,
        u.public_id AS subject_id FROM identity_access.staff s
        JOIN identity_access.roles r ON r.id=s.role_id JOIN identity_access.users u ON u.id=s.user_id""")
    for person in pool:
        city = (staff_cities or STAFF_CITIES).get(person["staff_code"])
        if person["city_id"] is None and city:
            if city not in valid_cities:
                raise ValueError(f"Invalid staff city: {city}")
            run("UPDATE identity_access.staff SET city_id=:city,updated_at=:now WHERE id=:id",
                city=city, now=now, id=person["id"])
            run("UPDATE identity_access.users SET auth_version=auth_version+1,version=version+1 WHERE id=:id",
                id=person["user_id"])
            run("""UPDATE identity_access.auth_sessions SET status='revoked',revoked_at=:now,
                revoke_reason='city_assigned' WHERE user_id=:uid AND status='active'""",
                now=now, uid=person["user_id"])
            audit("staff_city_assigned", {"city_id": city}, person["user_id"])
            person["city_id"] = city
            counts["staff_cities_assigned"] += 1
    by_staff = {r["public_id"]: r for r in pool}
    properties = rows("SELECT id,public_id,building_id,reference,address,city_id,attributes FROM property_leasing.properties")
    building_cities = {}
    for p in properties:
        city = mapping.get(p["reference"]) or p["city_id"]
        if city and p["building_id"]:
            previous = building_cities.setdefault(p["building_id"], city)
            if previous != city:
                raise ValueError("One building maps to multiple cities; resolve source data first")
    for b in rows("SELECT id,address,city_id FROM property_leasing.buildings"):
        # Demo addresses explicitly include the city. Never equate a state with a city.
        city = building_cities.get(b["id"]) or b["city_id"]
        if city is None:
            import re
            matches = [v for v in valid_cities if re.search(r"\b" + re.escape(v) + r"\b", b["address"], re.I)]
            city = matches[0] if len(matches) == 1 else None
        if city != b["city_id"]:
            run("UPDATE property_leasing.buildings SET city_id=:city WHERE id=:id", city=city, id=b["id"])
            counts["building_cities_assigned"] += 1
    for p in properties:
        if p["building_id"] is None and mapping.get(p["reference"]) != p["city_id"] and p["reference"] in mapping:
            run("UPDATE property_leasing.properties SET city_id=:city WHERE id=:id",
                city=mapping[p["reference"]], id=p["id"])
    buildings = rows("SELECT * FROM property_leasing.buildings")
    properties = rows("SELECT * FROM property_leasing.properties")
    by_building = {b["id"]: b for b in buildings}
    by_property = {p["id"]: p for p in properties}
    def expire_scope(table, scope):
        audit("city_scope_ended", {"table": table, "before": scope})
        if scope["valid_from"] >= now:
            # Preserve a cancelled future grant in audit, rather than leaving it effective later.
            run(f"DELETE FROM property_leasing.{table} WHERE id=:id", id=scope["id"])
        else:
            run(f"UPDATE property_leasing.{table} SET valid_until=:now,updated_at=:now WHERE id=:id",
                now=now, id=scope["id"])
        counts["scopes_ended"] += 1
    kept_primary = set()
    future_primary_start = {}
    for table, field, lookup in (("staff_building_scopes", "building_id", by_building),
                                  ("staff_property_scopes", "property_id", by_property)):
        for scope in rows(f"SELECT * FROM property_leasing.{table} WHERE valid_until IS NULL OR valid_until>:now", now=now):
            person, resource = by_staff.get(scope["staff_id"]), lookup.get(scope[field])
            good = person and resource and same_city(person["city_id"], resource["city_id"])
            if good and table == "staff_building_scopes" and scope["scope_role"] == "primary_manager":
                good = (person["role"] == "property_manager" and person["employment_status"] == "active"
                        and person["status"] == "active" and person["role_status"] == "active")
                # A legitimate same-city future handoff is not a duplicate of
                # today's primary manager, and must not be cancelled by sync.
                if good and scope["valid_from"] <= now:
                    good = scope[field] not in kept_primary
                if good and scope["valid_from"] <= now:
                    kept_primary.add(scope[field])
                elif good:
                    planned = future_primary_start.get(scope[field])
                    future_primary_start[scope[field]] = min(planned, scope["valid_from"]) if planned else scope["valid_from"]
            if not good:
                expire_scope(table, scope)
    admins = [p for p in pool if p["role"] == "manager_admin" and p["status"] == "active"
              and p["employment_status"] == "active"]
    if not admins:
        raise ValueError("An active administrator is required to record the migration")
    admin = sorted(admins, key=lambda r: r["staff_code"])[0]
    gaps = Counter()
    for b in buildings:
        manager = pick_staff(pool, "property_manager", b["city_id"], b["public_id"])
        if not manager:
            gaps[b["city_id"] or "unknown"] += 1
        elif b["id"] not in kept_primary:
            # Fill today's gap without extending a new grant across a valid
            # scheduled handoff. Future scopes are retained exactly as planned.
            valid_until = future_primary_start.get(b["id"])
            run("""INSERT INTO property_leasing.staff_building_scopes
                (staff_id,building_id,scope_role,valid_from,valid_until,assigned_by_subject_id)
                VALUES (:staff,:building,'primary_manager',:now,:until,:actor)""",
                staff=manager["public_id"], building=b["id"], now=now, until=valid_until, actor=admin["subject_id"])
            audit("city_scope_created", {"building_id": b["public_id"], "staff_id": manager["public_id"],
                                         "valid_until": valid_until})
            counts["building_scopes_created"] += 1
    for p in properties:
        consultant = pick_staff(pool, "leasing_consultant", p["city_id"], p["public_id"])
        attrs = dict(p["attributes"])
        attrs["consultant"] = ({"id": str(consultant["public_id"]), "staff_code": consultant["staff_code"],
                                "display_name": consultant["display_name"]} if consultant else None)
        if attrs != p["attributes"] and p["parking_spaces"] is not None:
            run("UPDATE property_leasing.properties SET attributes=CAST(:attrs AS jsonb) WHERE id=:id",
                attrs=json.dumps(attrs, ensure_ascii=False), id=p["id"])
            counts["property_consultants_updated"] += 1
        if p["building_id"] is None:
            existing = rows("""SELECT id FROM property_leasing.staff_property_scopes WHERE property_id=:id
                AND access_level='manage' AND valid_from<=:now AND (valid_until IS NULL OR valid_until>:now)""",
                id=p["id"], now=now)
            manager = pick_staff(pool, "property_manager", p["city_id"], p["public_id"])
            if manager and not existing:
                run("""INSERT INTO property_leasing.staff_property_scopes
                    (staff_id,property_id,access_level,source,valid_from,assigned_by_subject_id)
                    VALUES (:staff,:id,'manage','city_reconciliation',:now,:actor)""",
                    staff=manager["public_id"], id=p["id"], now=now, actor=admin["subject_id"])
                counts["property_scopes_created"] += 1
    for case in rows("SELECT * FROM property_leasing.prospect_cases WHERE status='open'"):
        prop = by_property.get(case["property_id"])
        if not prop:
            continue
        current = by_staff.get(case["assigned_consultant_staff_id"])
        if current and same_city(current["city_id"], prop["city_id"]):
            continue
        target = pick_staff(pool, "leasing_consultant", prop["city_id"], case["public_id"])
        target_id = target["public_id"] if target else None
        if target_id == case["assigned_consultant_staff_id"]:
            continue
        run("UPDATE property_leasing.prospect_cases SET assigned_consultant_staff_id=:target,version=version+1 WHERE id=:id",
            target=target_id, id=case["id"])
        run("""UPDATE property_leasing.prospect_contact_threads SET assigned_consultant_staff_id=:target
            WHERE prospect_case_id=:id AND status='active'""", target=target_id, id=case["id"])
        run("""INSERT INTO property_leasing.prospect_case_events
            (prospect_case_id,sequence_no,event_type,from_stage,to_stage,actor_subject_id,occurred_at,details_redacted)
            SELECT :id,COALESCE(max(sequence_no),0)+1,'consultant_reassigned',:stage,:stage,:actor,:now,CAST(:details AS jsonb)
            FROM property_leasing.prospect_case_events WHERE prospect_case_id=:id""",
            id=case["id"], stage=case["stage"], actor=admin["subject_id"], now=now,
            details=json.dumps({"reason": "city_reconciliation", "from_staff_id": str(case["assigned_consultant_staff_id"]),
                                "to_staff_id": str(target_id) if target_id else None}))
        counts["cases_reassigned"] += 1
    by_public_property = {p["public_id"]: p for p in properties}
    for order in rows("SELECT * FROM maintenance.maintenance_orders WHERE status NOT IN ('completed','cancelled')"):
        prop = by_public_property.get(order["property_id"])
        current = by_staff.get(order["assigned_staff_id"])
        if not prop or (current and same_city(current["city_id"], prop["city_id"])):
            continue
        target = pick_staff(pool, "maintainer", prop["city_id"], order["public_id"])
        target_id = target["public_id"] if target else None
        if target_id == order["assigned_staff_id"]:
            continue
        # A new worker starts with an assigned order; completed/cancelled history is untouched.
        status = "assigned" if target else "open"
        run("""UPDATE maintenance.maintenance_orders SET assigned_staff_id=:target,
            assigned_by_staff_id=:actor,assigned_at=:assigned,status=:status,version=version+1,
            next_event_sequence=next_event_sequence+1,updated_at=:now WHERE id=:id""",
            target=target_id, actor=admin["public_id"] if target else None,
            assigned=now if target else None, status=status, now=now, id=order["id"])
        run("""INSERT INTO maintenance.maintenance_events
            (public_id,order_id,sequence_no,actor_type,actor_subject_id,event_type,visibility,
             message,from_status,to_status,details)
            VALUES (:pid,:id,:seq,'staff',:actor,'order.city_reassigned','internal',
                    'City ownership reconciliation',:previous,:status,CAST(:details AS jsonb))""",
            pid=uuid4(), id=order["id"], seq=order["next_event_sequence"], actor=admin["subject_id"],
            previous=order["status"], status=status,
            details=json.dumps({"previous_staff_id": str(order["assigned_staff_id"]),
                                "assigned_staff_id": str(target_id) if target_id else None}))
        counts["work_orders_reassigned"] += 1
    return {"changes": dict(counts), "buildings_without_manager": dict(gaps),
            "properties_by_city": dict(Counter(p["city_id"] or "unknown" for p in properties))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            report = reconcile(connection, source_cities(args.dataset))
            if args.apply:
                transaction.commit()
            else:
                transaction.rollback()
        except BaseException:
            transaction.rollback()
            raise
    report["applied"] = args.apply
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
