#!/usr/bin/env python3
"""Integration QA against an explicitly named, disposable Docker PostgreSQL only."""
import argparse
import json
import hashlib
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sql", type=Path, required=True)
    parser.add_argument("--previous-root", type=Path)
    args = parser.parse_args()
    if not args.container.startswith("safescan-execution-data-qa-"):
        raise ValueError("Use a disposable safescan-execution-data-qa-* container")

    def sql(database, command=None, path=None, expect_failure=False):
        argv = ["docker", "exec", "-i", args.container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database]
        if path:
            with path.open("rb") as stream:
                result = subprocess.run(argv, stdin=stream, capture_output=True)
        else:
            result = subprocess.run(argv, input=command.encode(), capture_output=True)
        if expect_failure:
            if result.returncode == 0:
                raise AssertionError("Expected database rejection")
        elif result.returncode:
            raise RuntimeError(result.stderr.decode()[-1500:])
        return result.stdout.decode().strip(), result.stderr.decode()

    def create(database, template=None):
        sql("postgres", f"CREATE DATABASE {database}" + (f" TEMPLATE {template}" if template else "") + ";")

    summary = json.loads((args.root / "summary.json").read_text())
    names = list(summary["counts"])

    def counts(database):
        query = " UNION ALL ".join(f"SELECT '{name}',count(*) FROM collected_data.{name}" for name in names)
        result, _ = sql(database, query)
        return {line.split("|")[0]: int(line.split("|")[1]) for line in result.splitlines()}

    create("execution_final_fresh")
    sql("execution_final_fresh", path=args.root / "dataset.sql")
    if counts("execution_final_fresh") != summary["counts"]:
        raise AssertionError("Fresh database counts differ from manifest")
    sql("execution_final_fresh", path=args.root / "dataset.sql")
    if counts("execution_final_fresh") != summary["counts"]:
        raise AssertionError("Repeat import changed counts")
    print("Fresh + repeat import passed", flush=True)

    create("execution_final_baseline")
    sql("execution_final_baseline", path=args.baseline_sql)
    fingerprint = "SELECT md5(string_agg(to_jsonb(t)::text,'' ORDER BY id)) FROM collected_data.housing_records t WHERE id NOT LIKE 'au-20261031:%';"
    before, _ = sql("execution_final_baseline", fingerprint)
    create("execution_final_conflict", "execution_final_baseline")
    sql("execution_final_baseline", path=args.root / "dataset.sql")
    after, _ = sql("execution_final_baseline", fingerprint)
    if before != after:
        raise AssertionError("Existing housing facts changed")
    if counts("execution_final_baseline") != summary["counts"]:
        raise AssertionError("Existing-export import counts differ")
    print("Original baseline import + housing preservation passed", flush=True)

    sql("execution_final_conflict", "UPDATE collected_data.housing_records SET name='QA intentional conflicting name' WHERE id='general:hotham';")
    _, error = sql("execution_final_conflict", path=args.root / "dataset.sql", expect_failure=True)
    if "Dataset conflict in collected_data.housing_records" not in error:
        raise AssertionError("Import failed for an unexpected reason: " + error[-1000:])
    result, _ = sql("execution_final_conflict", "SELECT (SELECT count(*) FROM collected_data.housing_records), (SELECT count(*) FROM collected_data.media_assets), to_regclass('collected_data.execution_units') IS NULL;")
    if result != "58|339|t":
        raise AssertionError("Conflict import did not completely roll back: " + result)
    print("Conflicting baseline abort + transaction rollback passed", flush=True)

    _, wrong_unit_error = sql("execution_final_fresh", """UPDATE collected_data.simulated_inspections
SET unit_id=(SELECT id FROM collected_data.execution_units ORDER BY id DESC LIMIT 1)
WHERE id=(SELECT id FROM collected_data.simulated_inspections ORDER BY id LIMIT 1);""", expect_failure=True)
    if "foreign key constraint" not in wrong_unit_error:
        raise AssertionError("Cross-unit FK not enforced")
    null_fields, _ = sql("execution_final_fresh", """SELECT count(*) FROM collected_data.execution_property_profiles
WHERE address IS NULL OR property_type IS NULL OR bedrooms IS NULL OR bathrooms IS NULL
OR rooms_count IS NULL OR parking_spaces IS NULL OR floor_area_sqm IS NULL
OR whole_apartment_bedrooms IS NULL OR whole_apartment_bathrooms IS NULL;""")
    if null_fields != "0":
        raise AssertionError("Effective property fields contain nulls")
    upgraded = False
    if args.previous_root:
        create("execution_previous_version")
        sql("execution_previous_version", path=args.previous_root / "dataset.sql")
        create("execution_previous_conflict", "execution_previous_version")
        housing_fingerprint = "SELECT md5(string_agg(to_jsonb(t)::text,'' ORDER BY id)) FROM collected_data.housing_records t;"
        tenancy_fingerprint = "SELECT md5(string_agg(((to_jsonb(t)-'payload') || jsonb_build_object('payload',payload-'rent_basis'))::text,'' ORDER BY id)) FROM collected_data.simulated_tenancies t;"
        old_housing, _ = sql("execution_previous_version", housing_fingerprint)
        old_tenancies, _ = sql("execution_previous_version", tenancy_fingerprint)
        sql("execution_previous_version", path=args.root / "dataset.sql")
        if counts("execution_previous_version") != summary["counts"]:
            raise AssertionError("Previous-version upgrade changed record counts")
        if old_housing != sql("execution_previous_version", housing_fingerprint)[0]:
            raise AssertionError("Previous-version upgrade overwrote source housing")
        if old_tenancies != sql("execution_previous_version", tenancy_fingerprint)[0]:
            raise AssertionError("Previous-version upgrade changed tenancy history")
        sql("execution_previous_version", path=args.root / "dataset.sql")
        sql("execution_previous_conflict", """UPDATE collected_data.execution_units SET payload=jsonb_set(payload,'{observed_layout,bedrooms}','99')
WHERE id=(SELECT id FROM collected_data.execution_units ORDER BY id LIMIT 1);""")
        _, source_error = sql("execution_previous_conflict", path=args.root / "dataset.sql", expect_failure=True)
        if "Dataset conflict in collected_data.execution_units" not in source_error:
            raise AssertionError("Modified source fields were not rejected")
        unchanged, _ = sql("execution_previous_conflict", "SELECT count(*) FROM collected_data.execution_units WHERE payload ? 'property_fields_version';")
        if unchanged != "0":
            raise AssertionError("Failed upgrade did not roll back enriched attributes")
        upgraded = True
        print("Previous 500-unit version upgrade + immutable source protection passed", flush=True)
    result = {"postgres_version": sql("postgres", "SHOW server_version;")[0],
              "dataset_sql_sha256": hashlib.sha256((args.root / "dataset.sql").read_bytes()).hexdigest(),
              "fresh_import": True, "repeat_import": True, "existing_export_import": True,
              "baseline_housing_fingerprint_preserved": before == after,
              "conflict_import_rejected": True, "conflict_transaction_fully_rolled_back": True,
              "cross_unit_foreign_key_enforced": True, "counts": counts("execution_final_fresh"),
              "effective_property_null_rows": int(null_fields), "previous_500_unit_version_upgrade": upgraded,
              "test_environment": "network-isolated disposable Docker; no existing application database touched"}
    (args.root / "postgres_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
