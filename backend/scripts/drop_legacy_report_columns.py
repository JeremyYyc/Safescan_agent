import argparse
import sys
from pathlib import Path
from typing import Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import _ensure_core_tables, _ensure_report_table, _get_connection


LEGACY_COLUMNS = [
    "chat_id",
    "source_type",
    "source_path",
    "video_path",
    "region_info",
    "report_json",
    "representative_images",
]


def _load_columns(conn) -> List[str]:
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM reports")
        rows = cursor.fetchall() or []
    return [str(row[0]) for row in rows if row]


def _load_counts(conn) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM reports")
        counts["reports_total"] = int((cursor.fetchone() or [0])[0])
        cursor.execute("SELECT COUNT(*) FROM reports WHERE report_kind='analysis'")
        counts["reports_analysis"] = int((cursor.fetchone() or [0])[0])
        cursor.execute("SELECT COUNT(*) FROM reports WHERE report_kind='pdf'")
        counts["reports_pdf"] = int((cursor.fetchone() or [0])[0])
        cursor.execute("SELECT COUNT(*) FROM report_analysis")
        counts["report_analysis_rows"] = int((cursor.fetchone() or [0])[0])
        cursor.execute("SELECT COUNT(*) FROM report_pdf")
        counts["report_pdf_rows"] = int((cursor.fetchone() or [0])[0])
        cursor.execute("SELECT COUNT(*) FROM reports WHERE report_kind IS NULL OR report_kind=''")
        counts["reports_kind_missing"] = int((cursor.fetchone() or [0])[0])
    return counts


def _validate_ready(counts: Dict[str, int]) -> List[str]:
    issues: List[str] = []
    if counts.get("reports_kind_missing", 0) > 0:
        issues.append("reports.report_kind 存在空值")
    if counts.get("reports_analysis", 0) > counts.get("report_analysis_rows", 0):
        issues.append("analysis 主记录数量大于 report_analysis 子表数量")
    if counts.get("reports_pdf", 0) > counts.get("report_pdf_rows", 0):
        issues.append("pdf 主记录数量大于 report_pdf 子表数量")
    return issues


def migrate(*, apply: bool, force: bool) -> None:
    conn = _get_connection()
    if not conn:
        raise RuntimeError("Database is not configured")

    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)

        columns = _load_columns(conn)
        to_drop = [name for name in LEGACY_COLUMNS if name in set(columns)]
        counts = _load_counts(conn)
        issues = _validate_ready(counts)

        print("\n=== Legacy Columns Drop Check ===")
        print(f"mode: {'apply' if apply else 'dry-run'}")
        print(f"legacy_columns_found: {to_drop}")
        for key in (
            "reports_total",
            "reports_analysis",
            "reports_pdf",
            "report_analysis_rows",
            "report_pdf_rows",
            "reports_kind_missing",
        ):
            print(f"{key}: {counts.get(key, 0)}")
        if issues:
            print("validation_issues:")
            for issue in issues:
                print(f"- {issue}")
        else:
            print("validation_issues: none")

        if not apply:
            return
        if issues and not force:
            raise RuntimeError("Validation failed. Use --force if you still want to drop columns.")
        if not to_drop:
            print("No legacy columns to drop.")
            return

        with conn.cursor() as cursor:
            for column_name in to_drop:
                cursor.execute(f"ALTER TABLE reports DROP COLUMN {column_name}")
                print(f"dropped: reports.{column_name}")

        print("Drop completed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop legacy columns from reports table after v2 migration")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply column drops. Default is dry-run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force drop even if validation warnings exist.",
    )
    args = parser.parse_args()
    migrate(apply=bool(args.apply), force=bool(args.force))


if __name__ == "__main__":
    main()

