import argparse
import hashlib
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import (
    _ensure_chat_report_refs_table,
    _ensure_core_tables,
    _ensure_report_table,
    _get_connection,
)
from app.utils.uuid7 import uuid7_hex

BASE_DIR = BACKEND_DIR


def _normalize_path(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    return text.replace("\\", "/")


def _path_hash(normalized_path: str) -> str:
    return hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()


def _resolve_abs_path(raw_value: Any) -> Optional[Path]:
    text = str(raw_value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    try:
        if candidate.is_absolute():
            return candidate.resolve()
        return (BASE_DIR / candidate).resolve()
    except Exception:
        return None


def _safe_file_size(path: Optional[Path]) -> Optional[int]:
    if not path or not path.exists() or not path.is_file():
        return None
    try:
        return int(path.stat().st_size)
    except Exception:
        return None


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
    return None


def _dump_json(value: Any, fallback: Any) -> str:
    payload = value if value is not None else fallback
    return json.dumps(payload, ensure_ascii=False)


def _normalize_status(raw_status: Any) -> str:
    value = str(raw_status or "").strip().lower()
    if value in {"active", "archived", "deleted"}:
        return value
    return "active"


def _extract_report_title(report_json: Any) -> str:
    payload = _parse_json(report_json)
    if not isinstance(payload, dict):
        return ""
    title = str(payload.get("title") or "").strip()
    return title[:255]


def _extract_preview(report_json: Any) -> str:
    payload = _parse_json(report_json)
    if not isinstance(payload, dict):
        return ""
    preview = str(payload.get("content_preview") or "").strip()
    return preview[:8000]


def _normalize_image_list(value: Any) -> List[str]:
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        result = []
        for item in parsed:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    text = str(value or "").strip()
    return [text] if text else []


def _detect_report_kind(source_type: Any, source_path: Any) -> str:
    source_type_value = str(source_type or "").strip().lower()
    if source_type_value == "pdf":
        return "pdf"
    source_path_value = str(source_path or "").strip().lower()
    if source_path_value.endswith(".pdf"):
        return "pdf"
    return "analysis"


def _infer_title(
    *,
    report_id: int,
    existing_title: Any,
    report_json: Any,
    source_path: Any,
    chat_title: Any,
    report_kind: str,
) -> str:
    current_title = str(existing_title or "").strip()
    if current_title:
        return current_title[:255]
    from_json = _extract_report_title(report_json)
    if from_json:
        return from_json[:255]
    if report_kind == "pdf":
        source = str(source_path or "").strip()
        if source:
            try:
                stem = Path(source).stem.strip()
                if stem:
                    return stem[:255]
            except Exception:
                pass
    fallback_chat = str(chat_title or "").strip()
    if fallback_chat:
        return fallback_chat[:255]
    return f"Report {report_id}"


def _ensure_v2_tables(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "file_uuid CHAR(32) NOT NULL,"
            "user_id BIGINT NULL,"
            "storage_path TEXT NOT NULL,"
            "storage_path_hash CHAR(64) NOT NULL,"
            "mime_type VARCHAR(128) NULL,"
            "file_ext VARCHAR(16) NULL,"
            "file_size BIGINT NULL,"
            "sha256 CHAR(64) NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "UNIQUE KEY uniq_files_uuid (file_uuid),"
            "UNIQUE KEY uniq_files_storage_path_hash (storage_path_hash),"
            "INDEX idx_files_user (user_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute("SHOW COLUMNS FROM files")
        file_columns = {row[0] for row in cursor.fetchall()}
        if "storage_path_hash" not in file_columns:
            cursor.execute(
                "ALTER TABLE files "
                "ADD COLUMN storage_path_hash CHAR(64) NULL"
            )
        cursor.execute(
            "SELECT id, storage_path FROM files "
            "WHERE storage_path_hash IS NULL OR storage_path_hash=''"
        )
        pending_file_rows = cursor.fetchall() or []
        for row in pending_file_rows:
            file_id = int(row[0])
            path_value = _normalize_path(row[1])
            cursor.execute(
                "UPDATE files SET storage_path_hash=%s WHERE id=%s",
                (_path_hash(path_value), file_id),
            )
        cursor.execute(
            "ALTER TABLE files "
            "MODIFY COLUMN storage_path_hash CHAR(64) NOT NULL"
        )
        cursor.execute("SHOW INDEX FROM files")
        file_indexes = {row[2] for row in cursor.fetchall()}
        if "uniq_files_storage_path_hash" not in file_indexes:
            cursor.execute(
                "ALTER TABLE files "
                "ADD UNIQUE KEY uniq_files_storage_path_hash (storage_path_hash)"
            )
        if "uniq_files_storage_path" in file_indexes:
            cursor.execute(
                "ALTER TABLE files "
                "DROP INDEX uniq_files_storage_path"
            )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS report_analysis ("
            "report_id BIGINT PRIMARY KEY,"
            "video_file_id BIGINT NULL,"
            "region_info_json JSON NULL,"
            "report_json JSON NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_report_analysis_video_file (video_file_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS report_pdf ("
            "report_id BIGINT PRIMARY KEY,"
            "file_id BIGINT NOT NULL,"
            "pdf_kind VARCHAR(16) NOT NULL DEFAULT 'uploaded',"
            "derived_from_report_id BIGINT NULL,"
            "content_preview TEXT NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_report_pdf_file (file_id),"
            "INDEX idx_report_pdf_kind (pdf_kind),"
            "INDEX idx_report_pdf_derived (derived_from_report_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS report_assets ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "report_id BIGINT NOT NULL,"
            "file_id BIGINT NOT NULL,"
            "asset_kind VARCHAR(32) NOT NULL,"
            "sort_order INT NOT NULL DEFAULT 0,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "UNIQUE KEY uniq_report_asset (report_id, file_id, asset_kind),"
            "INDEX idx_report_assets_report (report_id),"
            "INDEX idx_report_assets_file (file_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )

        cursor.execute("SHOW COLUMNS FROM reports")
        columns = {row[0] for row in cursor.fetchall()}
        if "report_kind" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN report_kind VARCHAR(16) NULL"
            )
        if "origin_chat_id" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN origin_chat_id BIGINT NULL"
            )
        if "title" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN title VARCHAR(255) NULL"
            )
        if "status" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"
            )

        cursor.execute("SHOW INDEX FROM reports")
        indexes = {row[2] for row in cursor.fetchall()}
        if "idx_reports_kind" not in indexes:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD INDEX idx_reports_kind (report_kind)"
            )
        if "idx_reports_origin_chat" not in indexes:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD INDEX idx_reports_origin_chat (origin_chat_id)"
            )


def _load_tables(conn) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        rows = cursor.fetchall() or []
    result: set[str] = set()
    for row in rows:
        if not row:
            continue
        result.add(str(row[0]))
    return result


def _load_columns(conn, table_name: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        rows = cursor.fetchall() or []
    return {str(row[0]) for row in rows}


def _load_source_chat_map(conn) -> Dict[int, int]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT report_id, MIN(source_chat_id) AS source_chat_id "
            "FROM chat_report_refs "
            "WHERE source_chat_id IS NOT NULL "
            "GROUP BY report_id"
        )
        rows = cursor.fetchall() or []
    result: Dict[int, int] = {}
    for row in rows:
        report_id = row.get("report_id")
        source_chat_id = row.get("source_chat_id")
        if report_id is None or source_chat_id is None:
            continue
        result[int(report_id)] = int(source_chat_id)
    return result


def _load_analysis_by_chat(conn) -> Dict[int, List[Tuple[Any, int]]]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, chat_id, created_at "
            "FROM reports "
            "WHERE chat_id IS NOT NULL AND COALESCE(source_type, 'video') <> 'pdf' "
            "ORDER BY chat_id ASC, created_at ASC, id ASC"
        )
        rows = cursor.fetchall() or []
    result: Dict[int, List[Tuple[Any, int]]] = {}
    for row in rows:
        chat_id = row.get("chat_id")
        report_id = row.get("id")
        created_at = row.get("created_at")
        if chat_id is None or report_id is None:
            continue
        result.setdefault(int(chat_id), []).append((created_at, int(report_id)))
    return result


def _derive_analysis_report_id(
    *,
    origin_chat_id: Optional[int],
    pdf_created_at: Any,
    analysis_by_chat: Dict[int, List[Tuple[Any, int]]],
) -> Optional[int]:
    if origin_chat_id is None:
        return None
    candidates = analysis_by_chat.get(int(origin_chat_id)) or []
    if not candidates:
        return None
    chosen = None
    for created_at, report_id in candidates:
        if pdf_created_at is None or created_at is None:
            chosen = report_id
            continue
        if created_at <= pdf_created_at:
            chosen = report_id
        else:
            break
    if chosen is not None:
        return chosen
    return candidates[-1][1]


def _get_or_create_file_id(
    *,
    conn,
    cursor,
    file_cache: Dict[str, int],
    has_files_table: bool,
    user_id: Optional[int],
    raw_path: Any,
    apply: bool,
    summary: Dict[str, int],
) -> Optional[int]:
    normalized_path = _normalize_path(raw_path)
    if not normalized_path:
        return None
    storage_path_hash = _path_hash(normalized_path)
    if not has_files_table:
        summary["files_would_create"] += 1
        return None
    if normalized_path in file_cache:
        return file_cache[normalized_path]

    cursor.execute(
        "SELECT id, storage_path FROM files WHERE storage_path_hash=%s LIMIT 1",
        (storage_path_hash,),
    )
    row = cursor.fetchone()
    if row and row.get("id") is not None and _normalize_path(row.get("storage_path")) == normalized_path:
        file_id = int(row["id"])
        file_cache[normalized_path] = file_id
        summary["files_reused"] += 1
        return file_id
    if row and row.get("id") is not None:
        cursor.execute(
            "SELECT id FROM files WHERE storage_path=%s LIMIT 1",
            (normalized_path,),
        )
        exact_row = cursor.fetchone()
        if exact_row and exact_row.get("id") is not None:
            file_id = int(exact_row["id"])
            file_cache[normalized_path] = file_id
            summary["files_reused"] += 1
            return file_id

    if not apply:
        summary["files_would_create"] += 1
        return None

    resolved = _resolve_abs_path(normalized_path)
    size = _safe_file_size(resolved)
    mime_type, _ = mimetypes.guess_type(normalized_path)
    file_ext = Path(normalized_path).suffix.lower()[:16] or None
    for _ in range(5):
        try:
            cursor.execute(
                "INSERT INTO files (file_uuid, user_id, storage_path, storage_path_hash, mime_type, file_ext, file_size, sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)",
                (
                    uuid7_hex(),
                    int(user_id) if user_id is not None else None,
                    normalized_path,
                    storage_path_hash,
                    mime_type,
                    file_ext,
                    size,
                ),
            )
            file_id = int(cursor.lastrowid)
            file_cache[normalized_path] = file_id
            summary["files_created"] += 1
            return file_id
        except pymysql.IntegrityError:
            cursor.execute(
                "SELECT id FROM files WHERE storage_path=%s LIMIT 1",
                (normalized_path,),
            )
            retried = cursor.fetchone()
            if retried and retried.get("id") is not None:
                file_id = int(retried["id"])
                file_cache[normalized_path] = file_id
                summary["files_reused"] += 1
                return file_id
            continue
    return None


def migrate(apply: bool) -> None:
    conn = _get_connection()
    if not conn:
        raise RuntimeError("Database is not configured")

    summary: Dict[str, int] = {
        "reports_total": 0,
        "reports_updated": 0,
        "analysis_rows_upserted": 0,
        "pdf_rows_upserted": 0,
        "report_assets_upserted": 0,
        "files_created": 0,
        "files_reused": 0,
        "files_would_create": 0,
        "analysis_missing_video_file": 0,
        "pdf_missing_file": 0,
        "schema_missing_tables": 0,
        "schema_missing_columns": 0,
    }

    file_cache: Dict[str, int] = {}

    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        tables_before = _load_tables(conn)
        report_columns_before = _load_columns(conn, "reports")

        required_tables = {"files", "report_analysis", "report_pdf", "report_assets"}
        required_columns = {"report_kind", "origin_chat_id", "title", "status"}
        if not apply:
            summary["schema_missing_tables"] = len(required_tables - tables_before)
            summary["schema_missing_columns"] = len(required_columns - report_columns_before)
        else:
            _ensure_v2_tables(conn)

        tables_after = _load_tables(conn)
        report_columns_after = _load_columns(conn, "reports")
        files_columns_after: set[str] = set()
        if "files" in tables_after:
            files_columns_after = _load_columns(conn, "files")
        has_files_table = "files" in tables_after and "storage_path_hash" in files_columns_after

        source_chat_map = _load_source_chat_map(conn)
        analysis_by_chat = _load_analysis_by_chat(conn)

        select_report_kind = "r.report_kind" if "report_kind" in report_columns_after else "NULL AS report_kind"
        select_origin_chat_id = "r.origin_chat_id" if "origin_chat_id" in report_columns_after else "NULL AS origin_chat_id"
        select_title = "r.title" if "title" in report_columns_after else "NULL AS title"
        select_status = "r.status" if "status" in report_columns_after else "NULL AS status"

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT r.id, r.user_id, r.chat_id, r.source_type, r.source_path, r.video_path, "
                "r.region_info, r.report_json, r.representative_images, r.created_at, "
                f"{select_report_kind}, {select_origin_chat_id}, {select_title}, {select_status}, "
                "c.title AS chat_title "
                "FROM reports r LEFT JOIN chats c ON c.id=r.chat_id ORDER BY r.id ASC"
            )
            reports = cursor.fetchall() or []

        summary["reports_total"] = len(reports)

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            for row in reports:
                report_id = int(row["id"])
                user_id_raw = row.get("user_id")
                user_id = int(user_id_raw) if user_id_raw is not None else None

                report_kind = _detect_report_kind(row.get("source_type"), row.get("source_path"))
                existing_origin_chat_id = row.get("origin_chat_id")
                source_chat_id = source_chat_map.get(report_id)
                if existing_origin_chat_id is not None:
                    origin_chat_id = int(existing_origin_chat_id)
                elif row.get("chat_id") is not None:
                    origin_chat_id = int(row["chat_id"])
                elif source_chat_id is not None:
                    origin_chat_id = int(source_chat_id)
                else:
                    origin_chat_id = None

                title = _infer_title(
                    report_id=report_id,
                    existing_title=row.get("title"),
                    report_json=row.get("report_json"),
                    source_path=row.get("source_path"),
                    chat_title=row.get("chat_title"),
                    report_kind=report_kind,
                )
                status = _normalize_status(row.get("status"))

                should_update_report = (
                    str(row.get("report_kind") or "").strip().lower() != report_kind
                    or row.get("origin_chat_id") != origin_chat_id
                    or str(row.get("title") or "").strip() != title
                    or str(row.get("status") or "").strip().lower() != status
                )

                if should_update_report:
                    summary["reports_updated"] += 1
                    if apply:
                        cursor.execute(
                            "UPDATE reports "
                            "SET report_kind=%s, origin_chat_id=%s, title=%s, status=%s "
                            "WHERE id=%s",
                            (report_kind, origin_chat_id, title, status, report_id),
                        )

                if report_kind == "analysis":
                    video_file_id = _get_or_create_file_id(
                        conn=conn,
                        cursor=cursor,
                        file_cache=file_cache,
                        has_files_table=has_files_table,
                        user_id=user_id,
                        raw_path=row.get("video_path"),
                        apply=apply,
                        summary=summary,
                    )
                    if row.get("video_path") and not video_file_id:
                        summary["analysis_missing_video_file"] += 1

                    summary["analysis_rows_upserted"] += 1
                    if apply:
                        cursor.execute(
                            "INSERT INTO report_analysis (report_id, video_file_id, region_info_json, report_json) "
                            "VALUES (%s, %s, CAST(%s AS JSON), CAST(%s AS JSON)) "
                            "ON DUPLICATE KEY UPDATE "
                            "video_file_id=VALUES(video_file_id), "
                            "region_info_json=VALUES(region_info_json), "
                            "report_json=VALUES(report_json)",
                            (
                                report_id,
                                video_file_id,
                                _dump_json(_parse_json(row.get("region_info")), []),
                                _dump_json(_parse_json(row.get("report_json")), {}),
                            ),
                        )

                    images = _normalize_image_list(row.get("representative_images"))
                    for idx, image_path in enumerate(images):
                        image_file_id = _get_or_create_file_id(
                            conn=conn,
                            cursor=cursor,
                            file_cache=file_cache,
                            has_files_table=has_files_table,
                            user_id=user_id,
                            raw_path=image_path,
                            apply=apply,
                            summary=summary,
                        )
                        if image_file_id is None:
                            continue
                        summary["report_assets_upserted"] += 1
                        if apply:
                            cursor.execute(
                                "INSERT INTO report_assets (report_id, file_id, asset_kind, sort_order) "
                                "VALUES (%s, %s, %s, %s) "
                                "ON DUPLICATE KEY UPDATE sort_order=VALUES(sort_order)",
                                (report_id, image_file_id, "representative_image", idx),
                            )
                    continue

                pdf_file_id = _get_or_create_file_id(
                    conn=conn,
                    cursor=cursor,
                    file_cache=file_cache,
                    has_files_table=has_files_table,
                    user_id=user_id,
                    raw_path=row.get("source_path"),
                    apply=apply,
                    summary=summary,
                )
                if row.get("source_path") and not pdf_file_id:
                    summary["pdf_missing_file"] += 1

                pdf_kind = "exported" if source_chat_id is not None else "uploaded"
                derived_from_report_id = _derive_analysis_report_id(
                    origin_chat_id=origin_chat_id,
                    pdf_created_at=row.get("created_at"),
                    analysis_by_chat=analysis_by_chat,
                )

                if pdf_file_id is None:
                    continue
                summary["pdf_rows_upserted"] += 1
                if apply:
                    cursor.execute(
                        "INSERT INTO report_pdf (report_id, file_id, pdf_kind, derived_from_report_id, content_preview) "
                        "VALUES (%s, %s, %s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE "
                        "file_id=VALUES(file_id), "
                        "pdf_kind=VALUES(pdf_kind), "
                        "derived_from_report_id=VALUES(derived_from_report_id), "
                        "content_preview=VALUES(content_preview)",
                        (
                            report_id,
                            pdf_file_id,
                            pdf_kind,
                            derived_from_report_id,
                            _extract_preview(row.get("report_json")),
                        ),
                    )

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM reports")
            total_reports = int((cursor.fetchone() or {}).get("cnt") or 0)
            analysis_reports = 0
            pdf_reports = 0
            analysis_rows = 0
            pdf_rows = 0
            if "report_kind" in report_columns_after:
                cursor.execute("SELECT COUNT(*) AS cnt FROM reports WHERE report_kind='analysis'")
                analysis_reports = int((cursor.fetchone() or {}).get("cnt") or 0)
                cursor.execute("SELECT COUNT(*) AS cnt FROM reports WHERE report_kind='pdf'")
                pdf_reports = int((cursor.fetchone() or {}).get("cnt") or 0)
            if "report_analysis" in tables_after:
                cursor.execute("SELECT COUNT(*) AS cnt FROM report_analysis")
                analysis_rows = int((cursor.fetchone() or {}).get("cnt") or 0)
            if "report_pdf" in tables_after:
                cursor.execute("SELECT COUNT(*) AS cnt FROM report_pdf")
                pdf_rows = int((cursor.fetchone() or {}).get("cnt") or 0)

    print("\n=== Report Storage Migration Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"mode: {'apply' if apply else 'dry-run'}")
    print("\n=== Verification Snapshot ===")
    print(f"reports_total: {total_reports}")
    print(f"reports_analysis_kind: {analysis_reports}")
    print(f"reports_pdf_kind: {pdf_reports}")
    print(f"report_analysis_rows: {analysis_rows}")
    print(f"report_pdf_rows: {pdf_rows}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy reports table to v2 storage model")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration changes. Default is dry-run.",
    )
    args = parser.parse_args()
    migrate(apply=bool(args.apply))


if __name__ == "__main__":
    main()
