#!/usr/bin/env python3
"""Generate linked, explicitly simulated Australian rental execution fixtures."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil

from dataset_io import canonical_address, sha256, write_json, write_jsonl
from execution_dataset_sql import export_sql
from complete_property_fields import complete_units, completion_report

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "database/datasets/australia-execution-20261031"
AS_OF = date(2026, 10, 31)
FAULTS = [
    ("tap_drip", "厨房", "厨房水龙头持续滴水", "出水口在关闭后仍有间歇滴水，台面无明显积水。", "normal", "更换阀芯并复测关闭状态", 90, 180),
    ("slow_drain", "浴室", "淋浴排水缓慢", "淋浴区排水速度下降，使用后短时积水。", "normal", "清理存水弯及毛发堵塞并做通水测试", 100, 220),
    ("sealant_wear", "浴室", "淋浴密封胶老化", "淋浴屏边缘密封胶局部开裂，需安排补胶。", "low", "移除老化胶条并重新密封，记录固化时间", 120, 280),
    ("door_latch", "入口", "入户门锁舌卡顿", "门锁关闭时需重复调整，无法顺畅扣合。", "high", "调整锁扣位置并检查闭门器", 110, 260),
    ("window_latch", "起居区", "窗户锁扣松动", "开启和关闭时锁扣出现松动，五金需紧固。", "normal", "紧固五金并做开闭测试", 70, 160),
    ("light_flicker", "起居区", "顶灯间歇闪烁", "顶灯通电后偶发闪烁，其他用电设备正常。", "normal", "由维修人员检查灯具并更换损坏部件", 80, 190),
    ("alarm_fault", "入口", "烟雾报警器提示故障", "报警器出现非报警状态的故障提示，需安排检查。", "urgent", "安排合资格人员检查并记录功能测试结果", 110, 240),
    ("exhaust_noise", "浴室", "排气扇运转噪声增大", "排气扇启动后存在持续异响，仍能运转。", "low", "清洁扇叶并检修固定件及电机", 90, 210),
    ("sink_leak", "厨房", "水槽下方接头渗水", "排水接头外侧出现水珠，已放置接水容器。", "high", "更换密封圈并做连续排水测试", 130, 290),
    ("hot_water", "浴室", "热水供应异常", "热水流量和水温明显异常，需要检查供水设备。", "urgent", "由合资格人员检查热水系统并复测水温", 150, 390),
]


def stamp(day, hour=10):
    # Every timestamp carries an offset; unit payload also preserves local timezone.
    return datetime.combine(day, time(hour), timezone.utc).isoformat().replace("+00:00", "Z")


def synthetic(row):
    return {**row, "is_synthetic": True, "simulation_as_of": AS_OF.isoformat()}


def catalog(inputs, media_log, objects):
    baseline = json.loads((inputs / "baseline_housing_records.json").read_text())
    assets = json.loads((inputs / "baseline_media_assets.json").read_text())
    links = json.loads((inputs / "baseline_housing_media.json").read_text())
    public = json.loads((inputs / "public_sources.json").read_text())
    provenance = json.loads((inputs / "baseline_provenance.json").read_text())
    inventory = {r["id"]: r for r in baseline}
    media = {r["id"]: r for r in assets}
    media_refs = {(r["housing_id"], r["media_id"]): r for r in links}
    object_by_sha = {r["sha256"]: r for r in objects}
    addresses = defaultdict(list)
    for row in baseline:
        if row["address"]:
            addresses[canonical_address(row["address"])].append(row)
    aliases, checks = {}, []
    for record in public:
        duplicate = addresses.get(canonical_address(record["address"]), [])
        same_unit = [r for r in duplicate if record["record_type"] == "specific_property" and r["dataset_type"] == "general"]
        if same_unit:
            aliases[record["id"]] = same_unit[0]["id"]
            checks.append({"source_id": record["id"], "existing_ids": [r["id"] for r in same_unit], "action": "reuse_existing_specific_property"})
            continue
        if duplicate:
            checks.append({"source_id": record["id"], "existing_ids": [r["id"] for r in duplicate],
                           "action": "distinct_building_vs_room_type; original_fields_preserved"})
        inventory[record["id"]] = {k: record[k] for k in ("id", "dataset_type", "name", "city", "region", "address", "source_url")}
        inventory[record["id"]]["metadata"] = record
    for row in media_log:
        if row["status"] != "ok":
            continue
        obj = object_by_sha[row["id"]]
        if row["id"] not in media:
            media[row["id"]] = {"id": row["id"], "bucket": obj["bucket"], "object_key": obj["object_key"],
                "mime_type": row["mime_type"], "byte_size": row["byte_size"], "width": row["width"], "height": row["height"],
                "source_url": row["url"], "metadata": {"source_url": row["url"], "retrieved_on": "2026-10-31",
                    "rights_status": "unknown", "role": "marketing_reference_only; not inspection_or_fault_evidence"}}
        for ref in row["refs"]:
            housing = aliases.get(ref["housing_id"], ref["housing_id"])
            media_refs.setdefault((housing, row["id"]), {"housing_id": housing, "media_id": row["id"], "role": ref["role"]})
    repository_address_matches = [{"source_id": r["id"], "repository_address": address}
        for r in public for address in provenance["repository_fixture_addresses"]
        if canonical_address(r["address"]) == canonical_address(address)]
    return inventory, media, list(media_refs.values()), {
        "baseline_housing_count": len(baseline), "baseline_media_count": len(assets),
        "public_source_records": len(public), "new_housing_records": len(inventory) - len(baseline),
        "baseline_records_unchanged": all(inventory[r["id"]] == r for r in baseline),
        "baseline_sql_sha256": provenance["sql_sha256"],
        "repository_reserved_references": provenance["repository_reserved_references"],
        "repository_fixture_address_matches": repository_address_matches,
        "same_address_reviews": checks, "conflicting_overwrites": 0,
        "comparison_scope": "the supplied 20261020 SQL/MinIO export and repository seed/mock literals; no live database comparison",
        "aliases": aliases}


def room_options(housing):
    meta = housing["metadata"]
    if meta.get("room_types"):
        return meta["room_types"]
    return [{"name": meta.get("name", housing["name"]), "bedrooms": meta.get("bedrooms"),
             "bathrooms": meta.get("bathrooms"), "area_sqm": meta.get("area_sqm"),
             "weekly_rent": None, "rent_basis": "unknown", "source_url": housing["source_url"]}]


def generate(inventory, links, count, seed, media_url_ids=None, property_supplemental=None):
    if count < len(inventory):
        raise ValueError(f"--units must be at least {len(inventory)} to cover each source once")
    ordered = sorted(inventory.values(), key=lambda r: r["id"])
    # Exact residential listings receive one logical unit each. Only building/room-type
    # references can back additional hypothetical rooms.
    expandable = [r for r in ordered if r["dataset_type"] == "student" or r["metadata"].get("record_type") == "floorplan"]
    media_url_ids = media_url_ids or {}
    unit_media = defaultdict(list)
    building_media = defaultdict(list)
    for row in links:
        unit_media[row["housing_id"]].append(row["media_id"])
        if row["role"] == "building_marketing":
            building_media[row["housing_id"]].append(row["media_id"])
    tables = {k: [] for k in ("execution_units", "simulated_residents", "simulated_tenancies", "simulated_inspections",
                               "simulated_findings", "simulated_work_orders", "simulated_work_order_events", "execution_scenarios")}
    for index in range(count):
        lease_offset = len(tables["simulated_tenancies"])
        work_offset = len(tables["simulated_work_orders"])
        rng = random.Random(f"{seed}:unit:{index}")
        housing = ordered[index] if index < len(ordered) else expandable[(index - len(ordered)) % len(expandable)]
        room = rng.choice(room_options(housing))
        # Do not attach photographs of another room type in the same building.
        marketing_ids = sorted(set(building_media[housing["id"]] + [media_url_ids[i["url"]]
            for i in room.get("images", []) if i["url"] in media_url_ids])) if housing["id"].startswith("au-20261031:") else sorted(set(unit_media[housing["id"]]))
        is_student = housing["dataset_type"] == "student"
        uid = f"SIM-AU26-{seed}-U{index + 1:05d}"
        state = (housing.get("region") or {"Sydney": "NSW", "Melbourne": "VIC", "Brisbane": "QLD", "Adelaide": "SA", "Perth": "WA"}.get(housing.get("city")) or "VIC")
        tz = {"NSW": "Australia/Sydney", "VIC": "Australia/Melbourne", "QLD": "Australia/Brisbane", "SA": "Australia/Adelaide", "WA": "Australia/Perth"}.get(state, "Australia/Sydney")
        bedrooms = room.get("bedrooms")
        bathrooms = room.get("bathrooms")
        assumed_beds = bedrooms if bedrooms is not None else (0 if is_student else rng.choice([1, 2, 2, 3]))
        assumed_baths = bathrooms if bathrooms is not None else (1 if assumed_beds <= 2 else 2)
        shared = is_student and (assumed_beds > 1 or any(word in room["name"].lower() for word in ("share", "multishare")))
        scope = "private_room" if shared else ("studio" if assumed_beds == 0 else "entire_property")
        base_rent = room.get("weekly_rent")
        if not base_rent:
            base_rent = (350 if shared else 490) if is_student else 500 + 130 * assumed_beds
            base_rent += {"NSW": 100, "VIC": 30, "QLD": 20, "SA": -60, "WA": -20}.get(state, 0)
        weekly = max(200, int(round((base_rent + rng.randrange(-30, 35, 5)) / 5) * 5))
        occupancy = ("active" if index % 20 < 14 else "reserved" if index % 20 < 17 else "vacant")
        available = housing["metadata"].get("listed_available_from")
        if available and available[:10] > AS_OF.isoformat():
            occupancy = "reserved" if index % 2 else "vacant"
        unit = synthetic({"id": uid, "housing_id": housing["id"], "reference": uid, "source_room_type": room["name"],
            "scenario_status": occupancy, "weekly_rent": weekly, "currency": "AUD", "timezone": tz,
            "simulated_unit_label": f"SIM-{index + 1:05d}", "physical_unit_number": None,
            "source_address": housing["address"], "source_url": room.get("source_url") or housing["source_url"],
            "rental_scope": scope, "observed_layout": {k: room.get(k) for k in ("bedrooms", "bathrooms", "area_sqm", "area_scope", "rent_basis", "weekly_rent")},
            "simulation_layout": {"bedrooms": 1 if shared else assumed_beds, "bathrooms": 1 if shared else assumed_baths,
                "whole_apartment_bedrooms": bedrooms, "layout_assumed": bedrooms is None or bathrooms is None,
                "has_private_bathroom": not shared or (bathrooms is not None and bathrooms >= assumed_beds)},
            "marketing_media_ids": marketing_ids, "inspection_evidence_media_ids": [],
            "simulation_note": "Hypothetical inventory and occupancy; source photos illustrate a building/room type and never prove a unit's condition."})
        tables["execution_units"].append(unit)
        term = rng.choice([168, 336]) if is_student else rng.choice([182, 364])
        current_start = AS_OF - timedelta(days=rng.randint(35, min(130, term - 15)))
        if occupancy == "active":
            anchor_end = current_start - timedelta(days=rng.randint(7, 20))
        else:
            anchor_end = AS_OF - timedelta(days=rng.randint(15, 60))
        intervals = []
        for _ in range(rng.randint(2, 4)):
            duration = rng.choice([168, 336]) if is_student else rng.choice([182, 364])
            start = anchor_end - timedelta(days=duration - 1)
            intervals.append((start, anchor_end, "ended"))
            anchor_end = start - timedelta(days=rng.randint(7, 28))
        intervals.reverse()
        if occupancy == "active":
            intervals.append((current_start, current_start + timedelta(days=term - 1), "active"))
        elif occupancy == "reserved":
            future = AS_OF + timedelta(days=rng.randint(14, 60))
            if available:
                future = max(future, date.fromisoformat(available[:10]))
            intervals.append((future, future + timedelta(days=term - 1), "executed"))
        unit["simulation_history_assumption"] = "Historical tenancy dates are hypothetical; no claim of actual operation before collection date."
        for lease_index, (start, end, status) in enumerate(intervals, 1):
            tid, rid = uid + f"-L{lease_index}", uid + f"-R{lease_index}"
            resident = synthetic({"id": rid, "display_name": f"模拟住户 {index + 1:05d}-{lease_index}",
                "email": f"au26-{seed}-{index + 1}-{lease_index}@example.invalid", "phone": None})
            tables["simulated_residents"].append(resident)
            rent = int(round(weekly * (1 if status != "ended" else max(.78, 1 - (AS_OF - end).days / 6000)) / 5) * 5)
            tenancy = synthetic({"id": tid, "unit_id": uid, "resident_id": rid, "reference": tid,
                "starts_on": str(start), "ends_on": str(end), "status": status, "weekly_rent": rent,
                "currency": "AUD", "rent_basis": "room_per_week" if shared else "property_per_week",
                "occupants": 1 if is_student else max(1, min(assumed_beds, rng.randint(1, 4))),
                "signed_at": stamp(min(AS_OF, start - timedelta(days=10))), "ended_at": stamp(end, 23) if status == "ended" else None})
            tables["simulated_tenancies"].append(tenancy)
            inspections = [(start, "move_in")]
            cursor = start + timedelta(days=90)
            while cursor < min(end, AS_OF):
                inspections.append((cursor, "routine"))
                cursor += timedelta(days=90)
            if status == "ended":
                inspections.append((end, "move_out"))
            elif status == "active" and index % 3 == 0:
                inspections.append((AS_OF - timedelta(days=2), "routine"))
            incident_index = 0

            def incident(day, inspection_id=None, finding_id=None):
                nonlocal incident_index
                incident_index += 1
                fault = rng.choice(FAULTS)
                code, location, summary, symptom, priority, resolution, low, high = fault
                wid = tid + f"-W{incident_index:02d}"
                recent = status == "active" and (AS_OF - day).days <= 10
                work_status = rng.choice(["open", "assigned", "in_progress", "blocked", "completed", "cancelled"]) if recent else rng.choices(["completed", "cancelled"], [96, 4])[0]
                finished = min(day + timedelta(days=1 if priority == "urgent" else rng.randint(2, 8)), end, AS_OF)
                cost = rng.randrange(low, high + 1, 5) if work_status == "completed" else 0
                order = synthetic({"id": wid, "unit_id": uid, "tenancy_id": tid, "reported_by_resident_id": rid,
                    "inspection_id": inspection_id, "finding_id": finding_id, "reference": wid,
                    "category": code, "location": location, "summary": summary, "description": symptom,
                    "priority": priority, "status": work_status, "reported_at": stamp(day, 11),
                    "assigned_staff_reference": f"SIM-MAINT-{state}-01" if work_status not in ("open", "cancelled") else None,
                    "completed_at": stamp(finished, 16) if work_status == "completed" else None,
                    "cancelled_at": stamp(finished, 16) if work_status == "cancelled" else None,
                    "cost_aud": cost, "resolution": resolution if work_status == "completed" else None,
                    "blocked_reason": "等待匹配配件到货，已记录后续跟进日期" if work_status == "blocked" else None,
                    "evidence_media_ids": [], "condition_evidence": "synthetic_text_only"})
                tables["simulated_work_orders"].append(order)
                states = ["open"]
                if work_status in ("assigned", "in_progress", "blocked", "completed"):
                    states.append("assigned")
                if work_status in ("in_progress", "blocked", "completed"):
                    states.append("in_progress")
                if work_status in ("blocked", "completed", "cancelled"):
                    states.append(work_status)
                for sequence, to_status in enumerate(states, 1):
                    event_day = finished if to_status in ("completed", "cancelled") else day
                    tables["simulated_work_order_events"].append(synthetic({"id": wid + f"-E{sequence}", "work_order_id": wid,
                        "sequence_no": sequence, "from_status": states[sequence - 2] if sequence > 1 else None,
                        "to_status": to_status, "occurred_at": stamp(event_day, 16 if to_status in ("completed", "cancelled") else 10 + sequence),
                        "message": {"open": "已登记模拟报修", "assigned": "已安排模拟维修人员", "in_progress": "维修处理中",
                                    "blocked": "等待配件", "completed": resolution, "cancelled": "模拟住户确认无需维修，已记录取消原因"}[to_status]}))
                return fault, order

            for inspection_index, (day, kind) in enumerate(sorted(set(inspections)), 1):
                iid = tid + f"-I{inspection_index:02d}"
                planned = day > AS_OF
                findings = []
                if not planned and rng.random() < .55:
                    fid = iid + "-F01"
                    fault, order = incident(day, iid, fid)
                    findings.append(fid)
                    tables["simulated_findings"].append(synthetic({"id": fid, "inspection_id": iid, "unit_id": uid,
                        "tenancy_id": tid, "work_order_id": order["id"], "category": fault[0], "location": fault[1],
                        "description": fault[3], "severity": {"urgent": "high", "high": "medium", "normal": "low", "low": "low"}[fault[4]],
                        "observed_at": stamp(day), "evidence_media_ids": []}))
                tables["simulated_inspections"].append(synthetic({"id": iid, "unit_id": uid, "tenancy_id": tid,
                    "kind": kind, "status": "planned" if planned else "completed", "scheduled_at": stamp(day),
                    "completed_at": None if planned else stamp(day), "inspector_reference": f"SIM-INSPECT-{state}-01",
                    "finding_ids": findings, "checklist": ["入户门锁", "可见给排水", "照明", "通风", "报警器状态"],
                    "summary": "待执行模拟入住检查" if planned else ("发现待跟进事项，已关联模拟工单" if findings else "本次模拟检查无新增缺陷"),
                    "evidence_media_ids": [], "not_a_video_analysis_result": True}))
            if status != "executed":
                latest_day = min(end, AS_OF)
                for _ in range(rng.randint(1, 3)):
                    day = start + timedelta(days=rng.randint(1, max(1, (latest_day - start).days - 1)))
                    incident(day)
                if status == "active" and index % 4 == 1:
                    incident(AS_OF - timedelta(days=1))
        tables["execution_scenarios"].append(synthetic({"id": uid + "-CASE", "unit_id": uid,
            "intent": "租住历史、检查及报修关联查询", "prompt_zh": f"查询 {uid} 的租住历史，列出最近检查发现的问题、对应工单以及尚未完成的维修。",
            "expected_tenancy_ids": [r["id"] for r in tables["simulated_tenancies"][lease_offset:]],
            "expected_open_work_order_ids": [r["id"] for r in tables["simulated_work_orders"][work_offset:] if r["status"] not in ("completed", "cancelled")]}))
    complete_units(tables, inventory, property_supplemental, seed=seed)
    return tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--units", type=int, default=500)
    parser.add_argument("--seed", type=int, default=31)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    objects = json.loads((args.output / "objects.json").read_text())
    media_log = json.loads((args.output / "media_collection_log.json").read_text())
    inventory, media, links, audit = catalog(args.inputs, media_log, objects)
    if not audit["baseline_records_unchanged"]:
        raise ValueError("Baseline housing facts changed")
    supplemental = json.loads((args.inputs / "property_supplemental_sources.json").read_text())
    tables = generate(inventory, links, args.units, args.seed, {r["url"]: r["id"] for r in media_log if r["status"] == "ok"}, supplemental)
    profiles = [u["property_profile"] for u in tables["execution_units"]]
    completion = completion_report(profiles)
    write_jsonl(args.output / "property_profiles.jsonl", profiles)
    write_json(args.output / "property_completion_report.json", completion)
    audit["repository_reference_collisions"] = sorted({r["reference"] for r in tables["execution_units"]} & set(audit["repository_reserved_references"]))
    if audit["repository_reference_collisions"]:
        raise ValueError("Generated references conflict with repository fixtures")
    tables = {"housing_records": list(inventory.values()), "media_assets": list(media.values()), "housing_media": links, **tables}
    for table, rows in tables.items():
        write_jsonl(args.output / (table + ".jsonl"), rows)
    write_json(args.output / "conflict_audit.json", audit)
    for name in ("public_sources.json", "collection_log.json", "baseline_provenance.json", "property_supplemental_sources.json"):
        shutil.copyfile(args.inputs / name, args.output / name)
    for name in ("upload_dataset_images.py", "validate_execution_dataset.py"):
        shutil.copyfile(Path(__file__).with_name(name), args.output / name)
    (args.output / "requirements.txt").write_text("minio>=7.2,<8\n")
    export_sql(args.output / "dataset.sql", tables)
    summary = {"as_of": str(AS_OF), "seed": args.seed, "counts": {k: len(v) for k, v in tables.items()},
        "public_source_providers": dict(Counter(r["provider"] for r in json.loads((args.inputs / "public_sources.json").read_text()))),
        "scenario_statuses": dict(Counter(r["scenario_status"] for r in tables["execution_units"])),
        "work_order_statuses": dict(Counter(r["status"] for r in tables["simulated_work_orders"])),
        "baseline_housing_preserved": len(inventory) - audit["new_housing_records"],
        "additional_housing_records": audit["new_housing_records"], "unique_local_images": len(objects),
        "new_unique_images": len(objects) - audit["baseline_media_count"],
        "image_bytes": sum(r["byte_size"] for r in objects),
        "all_execution_data_is_synthetic": True, "business_tables_written": False,
        "source_unit_numbers_invented": False, "baseline_conflicting_overwrites": 0}
    summary["property_field_completion"] = completion
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "manifest.json", {p.name: sha256(p) for p in sorted(args.output.iterdir()) if p.is_file() and p.name != "manifest.json"})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
