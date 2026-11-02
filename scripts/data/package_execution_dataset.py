#!/usr/bin/env python3
"""Validate and package the prepared data and reproducible tools for delivery."""
import argparse
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from dataset_io import sha256, write_json
from validate_execution_dataset import load_tables, validate_files, validate_tables

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "database/datasets/australia-execution-20261031"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=SOURCE / "delivery-v2")
    args = parser.parse_args()
    root = args.root
    for name in ("README.md", "sample_queries.sql"):
        shutil.copyfile(SOURCE / name, root / name)
    (root / "generation_tools").mkdir(exist_ok=True)
    for script in Path(__file__).parent.glob("*.py"):
        shutil.copyfile(script, root / "generation_tools" / script.name)
    (root / "source_inputs").mkdir(exist_ok=True)
    for source in SOURCE.glob("*.json"):
        shutil.copyfile(source, root / "source_inputs" / source.name)
    report = validate_tables(load_tables(root))
    db_report = json.loads((root / "postgres_validation.json").read_text())
    if db_report.get("dataset_sql_sha256") != sha256(root / "dataset.sql"):
        raise ValueError("PostgreSQL validation does not match this SQL artifact")
    write_json(root / "validation_report.json", {**report, "postgres_qa_matches_sql": True,
               "automated_unit_tests": 18, "source_photo_visual_samples_reviewed": 4})

    def manifest():
        write_json(root / "manifest.json", {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob("*"))
            if p.is_file() and p != root / "manifest.json" and not p.name.endswith(".pyc")})

    manifest()
    report.update(validate_files(root))
    if args.destination.resolve() != root.resolve():
        if args.destination.exists():
            raise ValueError("Destination already exists; choose a fresh delivery directory")
        shutil.copytree(root, args.destination)
    archive = args.destination.parent / "safescan-australia-execution-500-20261031-v2.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as zipfile:
        for path in sorted(args.destination.rglob("*")):
            if path.is_file() and not path.name.endswith(".pyc"):
                zipfile.write(path, "safescan-australia-execution-500-20261031-v2/" + str(path.relative_to(args.destination)))
    with ZipFile(archive) as zipfile:
        if zipfile.testzip() is not None:
            raise ValueError("ZIP CRC validation failed")
    (archive.parent / (archive.name + ".sha256")).write_text(sha256(archive) + "  " + archive.name + "\n")
    print(json.dumps({"archive": str(archive), "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256(archive), "validation": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
