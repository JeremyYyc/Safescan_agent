"""One manually selected sync step, executed in the existing service image."""

import argparse
import json
import os
from pathlib import Path

import psycopg
import sqlalchemy as sa


def database_url():
    value = os.getenv("PROPERTY_LEASING_DATABASE_URL") or os.environ["DATABASE_URL"]
    return sa.engine.make_url(value)


def apply_sql(path):
    # SQL comes from the validated local compiler, never directly from a source export.
    url = database_url().set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(Path(path).read_text(), prepare=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("collection", "dataset", "media", "city"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--create-buckets", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.step == "collection":
        from import_collected_data import prepare
        sql_path, report = prepare(args.source, args.output / "collection")
        apply_sql(sql_path)
        print(json.dumps({"step": "collection", "table_rows": report["table_rows"]}), flush=True)
    elif args.step == "dataset":
        from integrate_execution_dataset import compile_import
        sql_path = args.output / "execution.import.sql"
        compile_import(args.source, sql_path, preserve_existing=True)
        apply_sql(sql_path)
    elif args.step == "media":
        from minio import Minio
        from minio.error import S3Error
        from upload_dataset_images import upload
        client = Minio(os.getenv("MINIO_ENDPOINT", "gateway:9000"),
                       access_key=os.environ["MINIO_ACCESS_KEY"], secret_key=os.environ["MINIO_SECRET_KEY"],
                       secure=os.getenv("MINIO_SECURE", "false").lower() == "true")
        upload(args.source, client, S3Error, create_bucket=args.create_buckets)
    else:
        from reconcile_city_assignments import reconcile, source_cities
        engine = sa.create_engine(database_url())
        try:
            with engine.begin() as connection:
                report = reconcile(connection, source_cities(args.source))
            report["applied"] = True
            (args.output / "city-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False), flush=True)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
