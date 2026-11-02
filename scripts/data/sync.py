#!/usr/bin/env python3
"""Explicit, resumable data synchronization; Docker deployment never runs this.

The default is a no-network, no-write dry run. Pass --apply after reviewing the
printed plan. Steps are registered below and execute in dependency order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STEPS = ("staff", "dataset", "media", "city", "lease-pdf")
STEPS = {
    "bootstrap-admin": ("identity-access-service", "Create the configured first administrator explicitly"),
    "staff": ("identity-access-service", "Add missing development staff; retain passwords and existing assignments"),
    "collection": ("property-leasing-service", "Audit and upsert the independent collected_data source tables"),
    "dataset": ("property-leasing-service", "Append missing execution records; retain existing operational state"),
    "media": ("property-leasing-service", "Upload missing objects and verify existing bytes; reject conflicting objects"),
    "city": ("property-leasing-service", "Reconcile city ownership and staff/resource assignments with audit events"),
    "lease-pdf": ("property-leasing-service", "Materialize missing current-version lease PDFs in private MinIO"),
}


def select_steps(value):
    requested = DEFAULT_STEPS if value is None else tuple(value.split(","))
    if requested == ("all",):
        requested = tuple(key for key in STEPS if key != "bootstrap-admin")
    unknown = set(requested) - set(STEPS)
    if unknown or any(not key for key in requested):
        raise ValueError("Unknown steps: " + ", ".join(sorted(unknown)))
    return [key for key in STEPS if key in requested]


def create_plan(args):
    selected = select_steps(args.steps)
    source = args.source_dir.resolve() if args.source_dir else None
    collection = args.collection_dir.resolve() if args.collection_dir else source
    plan = []
    for step in selected:
        required = []
        directory = collection if step == "collection" else (source or collection if step == "media" else source)
        if step == "dataset":
            from validate_execution_dataset import TABLES
            required = [name + ".jsonl" for name in TABLES]
        elif step == "city":
            required = ["execution_units.jsonl", "housing_records.jsonl"]
        elif step == "collection":
            required = ["dataset.sql", "manifest.json", "objects.json"]
        elif step == "media":
            required = ["objects.json"]
        if required and directory is None:
            flag = "--collection-dir or --source-dir" if step == "collection" else "--source-dir"
            raise ValueError(f"{step} requires {flag}")
        missing = [name for name in required if not (directory / name).is_file()]
        if missing:
            raise ValueError(f"{step}: missing source files in {directory}: {', '.join(missing)}")
        plan.append({"step": step, "service": STEPS[step][0], "description": STEPS[step][1],
                     "source_dir": str(directory) if required else None})
        if step == "media" and args.collection_dir and collection != directory:
            if not (collection / "objects.json").is_file():
                raise ValueError(f"media: missing objects.json in {collection}")
            plan.append({"step": step, "service": STEPS[step][0], "description": STEPS[step][1],
                         "source_dir": str(collection)})
    return plan


def command_for(args, item):
    command = ["docker", "compose", "--file", str(ROOT / "docker-compose.yml")]
    if args.env_file:
        command += ["--env-file", str(args.env_file.resolve())]
    elif not (ROOT / ".env").exists():
        command += ["--env-file", str(ROOT / ".env.example")]
    if args.project_name:
        command += ["--project-name", args.project_name]
    command += ["run", "--rm", "--no-deps"]
    step = item["step"]
    if step == "staff":
        return command + ["-e", "IDENTITY_SEED_STAFF=true", "--entrypoint", "python",
                          item["service"], "-m", "app.seed_staff"]
    if step == "bootstrap-admin":
        return command + ["--entrypoint", "python", item["service"], "-m", "app.bootstrap_admin"]
    if step == "lease-pdf":
        return command + ["--entrypoint", "python", item["service"], "-m", "app.backfill_lease_pdfs"]
    output = args.output_dir.resolve()
    command += ["--volume", f"{ROOT / 'scripts/data'}:/sync/scripts/data:ro",
                "--volume", f"{item['source_dir']}:/source:ro",
                "--volume", f"{output}:/sync-output",
                "--entrypoint", "python", item["service"], "/sync/scripts/data/sync_worker.py", step,
                "--source", "/source", "--output", "/sync-output"]
    if args.create_buckets:
        command += ["--create-buckets"]
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Execution export directory (JSONL and objects.json)")
    parser.add_argument("--collection-dir", type=Path, help="Optional separate raw collected-data export")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/data-sync")
    parser.add_argument("--steps", help="Comma-separated step names, or all; default: " + ",".join(DEFAULT_STEPS))
    parser.add_argument("--env-file", type=Path, help="Existing deployment env file; values are never printed")
    parser.add_argument("--project-name", help="Existing Docker Compose deployment project")
    parser.add_argument("--create-buckets", action="store_true", help="Permit missing private media buckets to be created")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Execute the reviewed manual synchronization")
    mode.add_argument("--dry-run", action="store_true", help="Print the plan only (the default)")
    args = parser.parse_args(argv)
    try:
        plan = create_plan(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "steps": plan,
                      "output_dir": str(args.output_dir.resolve()),
                      "deployment_behavior": "No data sync runs during Docker startup"},
                     ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for item in plan:
        print(json.dumps({"starting_step": item["step"]}), flush=True)
        subprocess.run(command_for(args, item), cwd=ROOT, check=True)
        print(json.dumps({"completed_step": item["step"]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
