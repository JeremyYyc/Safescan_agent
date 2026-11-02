"""Manual sync regression on an explicitly migrated, isolated test database."""

from datetime import UTC, datetime, timedelta
from argparse import Namespace
import os
from pathlib import Path

import pytest
import sqlalchemy as sa

from dataset_io import write_jsonl
from generate_execution_dataset import generate
from integrate_execution_dataset import compile_import
from reconcile_city_assignments import reconcile
from sync_worker import apply_sql
from sync import create_plan


def write_fixture(directory, units=20):
    housing = {"student:test": {"id": "student:test", "dataset_type": "student", "name": "Test Studio",
                                "city": "Brisbane", "region": "QLD", "address": "1 Example Street Brisbane QLD",
                                "source_url": "https://example.invalid/test",
                                "metadata": {"record_type": "room_type", "bedrooms": 0, "bathrooms": 1}}}
    tables = {"housing_records": list(housing.values()), "media_assets": [], "housing_media": [],
              **generate(housing, [], units, 31)}
    for name, rows in tables.items():
        write_jsonl(directory / (name + ".jsonl"), rows)
    return tables


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires an isolated migrated PostgreSQL test DB")
def test_manual_dataset_reentry_preserves_runtime_state_slots_and_future_city_handoff(tmp_path, monkeypatch):
    url = sa.engine.make_url(os.environ["TEST_DATABASE_URL"])
    assert "test" in url.database.split("_")
    monkeypatch.setenv("PROPERTY_LEASING_DATABASE_URL", url.render_as_string(hide_password=False))
    tables = write_fixture(tmp_path)
    sql_path = tmp_path / "sync.sql"
    compile_import(tmp_path, sql_path, preserve_existing=True)
    apply_sql(sql_path)
    apply_sql(sql_path)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            count = connection.scalar(sa.text("SELECT count(*) FROM property_leasing.properties"))
            lease = connection.execute(sa.text("SELECT id FROM property_leasing.leases WHERE status='active' LIMIT 1")).scalar_one()
            connection.execute(sa.text("DELETE FROM property_leasing.customer_lease_slots WHERE lease_id=:id"), {"id": lease})
            connection.execute(sa.text("UPDATE property_leasing.leases SET status='ended',ended_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id": lease})
            connection.execute(sa.text("UPDATE property_leasing.properties SET weekly_rent=999 WHERE id=(SELECT property_id FROM property_leasing.leases WHERE id=:id)"), {"id": lease})
        apply_sql(sql_path)
        with engine.begin() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM property_leasing.customer_lease_slots WHERE lease_id=:id"), {"id": lease}) == 0
            assert connection.scalar(sa.text("SELECT status FROM property_leasing.leases WHERE id=:id"), {"id": lease}) == "ended"
            assert connection.scalar(sa.text("SELECT weekly_rent FROM property_leasing.properties WHERE id=(SELECT property_id FROM property_leasing.leases WHERE id=:id)"), {"id": lease}) == 999
            assert connection.scalar(sa.text("SELECT count(*) FROM property_leasing.properties")) == count
            current = connection.execute(sa.text("SELECT * FROM property_leasing.staff_building_scopes LIMIT 1")).mappings().one()
            handoff = datetime.now(UTC) + timedelta(days=1)
            connection.execute(sa.text("UPDATE property_leasing.staff_building_scopes SET valid_until=:day WHERE id=:id"), {"day": handoff, "id": current["id"]})
            future = connection.execute(sa.text("""INSERT INTO property_leasing.staff_building_scopes
                (staff_id,building_id,scope_role,valid_from,assigned_by_subject_id)
                VALUES (:staff,:building,'primary_manager',:day,:actor) RETURNING id"""),
                {"staff": current["staff_id"], "building": current["building_id"], "day": handoff,
                 "actor": current["assigned_by_subject_id"]}).scalar_one()
            mapping = {unit["reference"]: "brisbane" for unit in tables["execution_units"]}
            reconcile(connection, mapping)
            assert connection.scalar(sa.text("SELECT count(*) FROM property_leasing.staff_building_scopes WHERE id=:id AND valid_until IS NULL"), {"id": future}) == 1
            assert connection.scalar(sa.text("SELECT valid_until FROM property_leasing.staff_building_scopes WHERE id=:id"), {"id": current["id"]}) == handoff
        apply_sql(sql_path)  # Reentry after city reconciliation must retain its changes too.
    finally:
        engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires an isolated migrated PostgreSQL test DB")
def test_future_only_primary_handoff_limits_new_current_grant_without_overlap():
    url = sa.engine.make_url(os.environ["TEST_DATABASE_URL"])
    assert "test" in url.database.split("_")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            person = connection.execute(sa.text("""SELECT s.public_id AS staff_id,u.public_id AS subject_id
                FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id
                WHERE s.staff_code='PM003' AND s.city_id='brisbane'""")).mappings().one()
            building = connection.execute(sa.text("""INSERT INTO property_leasing.buildings
                (reference,name,address,city_id,timezone,status,attributes)
                VALUES ('B-FUTURE-ONLY-SYNC','Future-only handoff','Future Street Brisbane QLD',
                        'brisbane','Australia/Brisbane','active','{}') RETURNING id""")).scalar_one()
            handoff = datetime.now(UTC) + timedelta(days=2)
            future = connection.execute(sa.text("""INSERT INTO property_leasing.staff_building_scopes
                (staff_id,building_id,scope_role,valid_from,assigned_by_subject_id)
                VALUES (:staff,:building,'primary_manager',:handoff,:actor) RETURNING id"""),
                {"staff": person["staff_id"], "building": building, "handoff": handoff,
                 "actor": person["subject_id"]}).scalar_one()
            reconcile(connection, {})
            current = connection.execute(sa.text("""SELECT * FROM property_leasing.staff_building_scopes
                WHERE building_id=:building AND valid_from<=CURRENT_TIMESTAMP
                AND (valid_until IS NULL OR valid_until>CURRENT_TIMESTAMP)"""),
                {"building": building}).mappings().one()
            assert current["valid_until"] == handoff
            planned = connection.execute(sa.text("SELECT * FROM property_leasing.staff_building_scopes WHERE id=:id"),
                                         {"id": future}).mappings().one()
            assert planned["valid_from"] == handoff and planned["valid_until"] is None
            assert connection.scalar(sa.text("""SELECT count(*) FROM property_leasing.staff_building_scopes a
                JOIN property_leasing.staff_building_scopes b ON a.id<b.id AND a.building_id=b.building_id
                WHERE a.building_id=:building AND tstzrange(a.valid_from,a.valid_until,'[)')
                    && tstzrange(b.valid_from,b.valid_until,'[)')"""), {"building": building}) == 0
            reconcile(connection, {})
            assert connection.scalar(sa.text("SELECT count(*) FROM property_leasing.staff_building_scopes WHERE building_id=:building"),
                                     {"building": building}) == 2
    finally:
        engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires an isolated migrated PostgreSQL test DB")
def test_upgrade_from_original_twelve_staff_prepares_cities_before_closed_cases(tmp_path, monkeypatch):
    url = sa.engine.make_url(os.environ["TEST_DATABASE_URL"])
    assert "test" in url.database.split("_")
    monkeypatch.setenv("PROPERTY_LEASING_DATABASE_URL", url.render_as_string(hide_password=False))
    tables = write_fixture(tmp_path, units=21)
    engine = sa.create_engine(url)
    legacy = ("LC001", "LC002", "LC003", "LC004", "PM001", "PM002", "PM003", "PM004",
              "MT001", "MT002", "MT003", "MA001")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("UPDATE identity_access.staff SET city_id=NULL WHERE staff_code=ANY(:codes)"),
                               {"codes": list(legacy)})
            assert connection.scalar(sa.text("SELECT city_id FROM identity_access.staff WHERE staff_code='LC003'")) is None
        plan = create_plan(Namespace(steps="dataset,city", source_dir=tmp_path, collection_dir=None))
        mapping = {unit["reference"]: "brisbane" for unit in tables["execution_units"]}
        for item in plan:
            if item["step"] == "city":
                with engine.begin() as connection:
                    reconcile(connection, mapping)
            else:
                sql_path = tmp_path / "upgrade.sql"
                compile_import(tmp_path, sql_path, preserve_existing=True)
                apply_sql(sql_path)
        with engine.begin() as connection:
            expected = connection.scalar(sa.text("SELECT public_id FROM identity_access.staff WHERE staff_code='LC003'"))
            cases = connection.execute(sa.text("""SELECT c.assigned_consultant_staff_id FROM property_leasing.prospect_cases c
                JOIN property_leasing.properties p ON p.id=c.property_id
                WHERE p.reference=:reference AND c.status='closed'"""),
                {"reference": tables["execution_units"][-1]["reference"]}).scalars().all()
            assert cases, "The expanded export must add new historical closed cases"
            assert all(person == expected for person in cases), "City preparation must precede import; final reconciliation leaves closed cases unchanged"
            assert connection.scalar(sa.text("SELECT city_id FROM identity_access.staff WHERE staff_code='LC003'")) == "brisbane"
    finally:
        engine.dispose()
