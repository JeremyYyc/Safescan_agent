import json
import os
import hashlib
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import pymysql

from app.env import load_env
from app.utils.uuid7 import uuid7_hex

load_env()


_SCHEMA_MIGRATION_LOCK = threading.Lock()


def _is_mysql_operational_error(exc: Exception, *error_codes: int) -> bool:
    if not isinstance(exc, pymysql.err.OperationalError):
        return False
    if not exc.args:
        return False
    try:
        code = int(exc.args[0])
    except Exception:
        return False
    return code in set(error_codes)


def _parse_database_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("mysql+pymysql://"):
        url = "mysql://" + url[len("mysql+pymysql://"):]
    parsed = urlparse(url)
    if parsed.scheme != "mysql":
        return None
    database = parsed.path.lstrip("/")
    if not database:
        return None
    charset = parse_qs(parsed.query).get("charset", ["utf8mb4"])[0]
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username or "",
        "password": parsed.password or "",
        "database": database,
        "charset": charset,
    }


def _get_connection():
    config = _parse_database_url()
    if not config:
        return None
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset=config["charset"],
        autocommit=True,
    )


def is_db_available() -> bool:
    conn = _get_connection()
    if not conn:
        return False
    conn.close()
    return True


def _get_id(row, key: str = "id"):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[0]


def _ensure_core_tables(conn) -> None:
    with _SCHEMA_MIGRATION_LOCK:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "user_id INT AUTO_INCREMENT PRIMARY KEY,"
                "username VARCHAR(32),"
                "email VARCHAR(128),"
                "avatar VARCHAR(128),"
                "password VARCHAR(32),"
                "storage_uuid CHAR(32) NULL,"
                "create_time DATETIME,"
                "update_time DATETIME"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS chats ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "user_id BIGINT NULL,"
                "title VARCHAR(255),"
                "chat_type VARCHAR(16) NOT NULL DEFAULT 'report',"
                "status VARCHAR(32) NOT NULL DEFAULT 'active',"
                "pinned TINYINT(1) NOT NULL DEFAULT 0,"
                "last_message_at TIMESTAMP NULL,"
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "role VARCHAR(32) NOT NULL,"
                "content LONGTEXT NOT NULL,"
                "meta JSON NULL,"
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS chat_details ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "chat_id BIGINT NOT NULL,"
                "role VARCHAR(32) NOT NULL,"
                "message_id BIGINT NULL,"
                "report_id BIGINT NULL,"
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "INDEX idx_chat_details_chat_id_created (chat_id, created_at)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )

            cursor.execute("SHOW COLUMNS FROM chats")
            columns = {row[0] for row in cursor.fetchall()}
            if "pinned" not in columns:
                cursor.execute(
                    "ALTER TABLE chats "
                    "ADD COLUMN pinned TINYINT(1) NOT NULL DEFAULT 0"
                )
            if "chat_type" not in columns:
                cursor.execute(
                    "ALTER TABLE chats "
                    "ADD COLUMN chat_type VARCHAR(16) NOT NULL DEFAULT 'report'"
                )

            cursor.execute("SHOW COLUMNS FROM users")
            user_columns = {row[0] for row in cursor.fetchall()}
            if "storage_uuid" not in user_columns:
                try:
                    cursor.execute(
                        "ALTER TABLE users "
                        "ADD COLUMN storage_uuid CHAR(32) NULL"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1060):
                        raise

            cursor.execute("SELECT user_id FROM users WHERE storage_uuid IS NULL OR storage_uuid='' ")
            pending_user_ids = [row[0] for row in cursor.fetchall()]
            for user_id in pending_user_ids:
                cursor.execute(
                    "UPDATE users SET storage_uuid=%s WHERE user_id=%s",
                    (uuid7_hex(), user_id),
                )

            cursor.execute(
                "SELECT storage_uuid FROM users "
                "WHERE storage_uuid IS NOT NULL AND storage_uuid<>'' "
                "GROUP BY storage_uuid HAVING COUNT(*) > 1"
            )
            duplicate_values = [row[0] for row in cursor.fetchall()]
            for dup_uuid in duplicate_values:
                cursor.execute(
                    "SELECT user_id FROM users WHERE storage_uuid=%s ORDER BY user_id ASC",
                    (dup_uuid,),
                )
                dup_user_ids = [row[0] for row in cursor.fetchall()]
                for user_id in dup_user_ids[1:]:
                    cursor.execute(
                        "UPDATE users SET storage_uuid=%s WHERE user_id=%s",
                        (uuid7_hex(), user_id),
                    )

            cursor.execute("SHOW INDEX FROM users")
            user_indexes = {row[2] for row in cursor.fetchall()}
            if "uniq_users_storage_uuid" not in user_indexes:
                try:
                    cursor.execute(
                        "ALTER TABLE users "
                        "ADD UNIQUE KEY uniq_users_storage_uuid (storage_uuid)"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1061):
                        raise


def _hash_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_id, username, email, avatar, password, storage_uuid, create_time, update_time "
                "FROM users WHERE email=%s LIMIT 1",
                (email,),
            )
            return cursor.fetchone()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_id, username, email, avatar, password, storage_uuid, create_time, update_time "
                "FROM users WHERE username=%s LIMIT 1",
                (username,),
            )
            return cursor.fetchone()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_id, username, email, avatar, password, storage_uuid, create_time, update_time "
                "FROM users WHERE user_id=%s LIMIT 1",
                (user_id,),
            )
            return cursor.fetchone()


def ensure_user_storage_uuid(user_id: int) -> Optional[str]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT storage_uuid FROM users WHERE user_id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            current_value = str(row.get("storage_uuid") or "").strip()
            if current_value:
                return current_value

        for _ in range(5):
            candidate = uuid7_hex()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET storage_uuid=%s WHERE user_id=%s AND (storage_uuid IS NULL OR storage_uuid='')",
                        (candidate, user_id),
                    )
                    if cursor.rowcount > 0:
                        return candidate
            except pymysql.IntegrityError:
                continue

            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT storage_uuid FROM users WHERE user_id=%s LIMIT 1",
                    (user_id,),
                )
                row = cursor.fetchone()
                current_value = str((row or {}).get("storage_uuid") or "").strip()
                if current_value:
                    return current_value
    return None


def update_username(user_id: int, username: str) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET username=%s, update_time=NOW() WHERE user_id=%s",
                (username, user_id),
            )
            return cursor.rowcount >= 0


def create_user(email: str, username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        password_hash = _hash_password(password)
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    storage_uuid = uuid7_hex()
                    cursor.execute(
                        "INSERT INTO users (username, email, avatar, password, storage_uuid, create_time, update_time) "
                        "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                        (username, email, "", password_hash, storage_uuid),
                    )
                    user_id = cursor.lastrowid
                    return get_user_by_id(user_id)
            except pymysql.IntegrityError:
                continue
    return None


def verify_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user:
        return None
    password_hash = _hash_password(password)
    if user.get("password") != password_hash:
        return None
    return user


def create_chat(
    title: Optional[str] = None,
    user_id: Optional[int] = None,
    chat_type: str = "report",
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        if user_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chats (user_id, title, status, chat_type) VALUES (%s, %s, %s, %s)",
                (user_id, title or "New Chat", "active", chat_type),
            )
            return cursor.lastrowid


def get_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, user_id, title, status, pinned, chat_type, last_message_at, created_at, updated_at "
                "FROM chats WHERE id=%s",
                (chat_id,),
            )
            return cursor.fetchone()


def list_chats(
    user_id: Optional[int] = None, limit: int = 50, offset: int = 0
) -> Optional[List[Dict[str, Any]]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            params: List[Any] = []
            query = (
                "SELECT "
                "c.id, c.user_id, c.title, c.status, c.pinned, c.chat_type, "
                "c.last_message_at, c.created_at, c.updated_at, "
                "EXISTS(SELECT 1 FROM reports r WHERE r.chat_id=c.id AND COALESCE(r.source_type, 'video')='video') AS has_report "
                "FROM chats c"
            )
            if user_id is None:
                return []
            query += " WHERE user_id=%s"
            params.append(user_id)
            query += " ORDER BY COALESCE(last_message_at, updated_at) DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            cursor.execute(query, tuple(params))
            return cursor.fetchall()


def update_chat_title(chat_id: int, title: str) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE chats SET title=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (title, chat_id),
            )
            return cursor.rowcount > 0


def update_chat_metadata(
    chat_id: int,
    title: Optional[str] = None,
    pinned: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        fields: List[str] = []
        params: List[Any] = []
        if title is not None:
            fields.append("title=%s")
            params.append(title)
        if pinned is not None:
            fields.append("pinned=%s")
            params.append(1 if pinned else 0)
        if not fields:
            return get_chat(chat_id)
        params.append(chat_id)
        with conn.cursor() as cursor:
            if pinned is not None and title is None:
                cursor.execute(
                    f"UPDATE chats SET {', '.join(fields)} WHERE id=%s",
                    tuple(params),
                )
            else:
                cursor.execute(
                    f"UPDATE chats SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    tuple(params),
                )
        return get_chat(chat_id)


def delete_chat(chat_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM reports WHERE chat_id=%s",
                (chat_id,),
            )
            report_rows = cursor.fetchall()
            report_ids = [row[0] for row in report_rows if row and row[0]]
            if report_ids:
                placeholders = ", ".join(["%s"] * len(report_ids))
                cursor.execute(
                    f"UPDATE chat_report_refs SET status='deleted' "
                    f"WHERE report_id IN ({placeholders})",
                    tuple(report_ids),
                )
            cursor.execute(
                "SELECT message_id FROM chat_details "
                "WHERE chat_id=%s AND message_id IS NOT NULL",
                (chat_id,),
            )
            message_rows = cursor.fetchall()
            message_ids = [row[0] for row in message_rows if row and row[0]]
            if message_ids:
                placeholders = ", ".join(["%s"] * len(message_ids))
                cursor.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    tuple(message_ids),
                )
            if report_ids:
                placeholders = ", ".join(["%s"] * len(report_ids))
                cursor.execute(
                    f"DELETE FROM reports WHERE id IN ({placeholders})",
                    tuple(report_ids),
                )
            cursor.execute("DELETE FROM chat_details WHERE chat_id=%s", (chat_id,))
            cursor.execute("DELETE FROM chats WHERE id=%s", (chat_id,))
            return cursor.rowcount > 0


def add_chat_message(
    chat_id: int,
    role: str,
    content: str,
    user_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        if user_id is None:
            return None
        if role not in ("user", "assistant"):
            return None
        payload = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (role, content, meta) VALUES (%s, %s, %s)",
                (role, content, payload),
            )
            message_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO chat_details (chat_id, role, message_id, report_id) "
                "VALUES (%s, %s, %s, NULL)",
                (chat_id, role, message_id),
            )
            cursor.execute(
                "UPDATE chats SET last_message_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=%s",
                (chat_id,),
            )
            return message_id


def add_chat_report_detail(
    chat_id: int,
    report_id: int,
    user_id: Optional[int] = None,
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        if user_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_details (chat_id, role, message_id, report_id) "
                "VALUES (%s, %s, NULL, %s)",
                (chat_id, "report", report_id),
            )
            cursor.execute(
                "UPDATE chats SET last_message_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=%s",
                (chat_id,),
            )
            return cursor.lastrowid


def add_chat_report_ref(
    chat_id: int,
    report_id: int,
    source_chat_id: Optional[int] = None,
    status: str = "active",
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_report_refs (chat_id, report_id, source_chat_id, status) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE status=VALUES(status), updated_at=CURRENT_TIMESTAMP",
                (chat_id, report_id, source_chat_id, status),
            )
            # MySQL returns lastrowid=0 on duplicate-key update path.
            # Treat duplicate bind as success and return a stable non-None value.
            return cursor.lastrowid if cursor.lastrowid else 0


def set_chat_report_ref_status(chat_id: int, report_id: int, status: str) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    normalized_status = (status or "").strip().lower()
    if normalized_status not in ("active", "removed", "deleted"):
        return False
    # Backward compatibility: legacy "manual remove" may still pass deleted.
    # Real source-report deletion is handled by delete_chat() direct SQL update.
    if normalized_status == "deleted":
        normalized_status = "removed"
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_report_refs SET status=%s, updated_at=CURRENT_TIMESTAMP "
                "WHERE chat_id=%s AND report_id=%s",
                (normalized_status, chat_id, report_id),
            )
            return cursor.rowcount > 0


def list_chat_report_refs(chat_id: int) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, chat_id, report_id, source_chat_id, status, created_at, updated_at "
                "FROM chat_report_refs WHERE chat_id=%s ORDER BY created_at ASC",
                (chat_id,),
            )
            return cursor.fetchall()


def get_active_report_payloads_for_chat(chat_id: int) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT "
                "r.id AS report_id, r.chat_id AS source_chat_id, r.user_id AS user_id, "
                "r.source_type AS source_type, r.source_path AS source_path, "
                "r.video_path AS video_path, r.region_info AS region_info, "
                "r.report_json AS report_json, r.representative_images AS representative_images, "
                "r.created_at AS created_at "
                "FROM chat_report_refs cr "
                "JOIN reports r ON cr.report_id = r.id "
                "WHERE cr.chat_id=%s AND cr.status='active' "
                "ORDER BY cr.created_at ASC",
                (chat_id,),
            )
            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                results.append(
                    {
                        "report_id": row.get("report_id"),
                        "source_chat_id": row.get("source_chat_id"),
                        "user_id": row.get("user_id"),
                        "source_type": row.get("source_type"),
                        "source_path": row.get("source_path"),
                        "video_path": row.get("video_path"),
                        "region_info": _safe_parse_json(row.get("region_info")),
                        "report_json": _safe_parse_json(row.get("report_json")),
                        "representative_images": _safe_parse_json(row.get("representative_images")),
                        "created_at": row.get("created_at"),
                    }
                )
            return results


def get_latest_report_id(chat_id: int) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM reports WHERE chat_id=%s ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None


def get_latest_pdf_for_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT r.id AS report_id, r.source_path AS source_path, r.report_json AS report_json, r.created_at AS created_at "
                "FROM chat_report_refs cr "
                "JOIN reports r ON cr.report_id = r.id "
                "WHERE cr.chat_id=%s AND cr.status='active' AND r.source_type='pdf' AND cr.source_chat_id=%s "
                "ORDER BY r.created_at DESC LIMIT 1",
                (chat_id, chat_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            row["report_json"] = _safe_parse_json(row.get("report_json"))
            return row


def get_report(report_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, chat_id, user_id, source_type, source_path, video_path, region_info, report_json, "
                "representative_images, created_at "
                "FROM reports WHERE id=%s",
                (report_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            row["region_info"] = _safe_parse_json(row.get("region_info"))
            row["report_json"] = _safe_parse_json(row.get("report_json"))
            row["representative_images"] = _safe_parse_json(row.get("representative_images"))
            return row


def store_pdf_report(
    *,
    user_id: int,
    source_path: str,
    title: str,
    extracted_text: str = "",
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        safe_title = (title or "Uploaded PDF Report").strip()[:255] or "Uploaded PDF Report"
        preview_text = (extracted_text or "").strip()[:8000]
        report_payload = json.dumps(
            {
                "title": safe_title,
                "source_type": "pdf",
                "summary": "",
                "content_preview": preview_text,
            },
            ensure_ascii=False,
        )
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reports (chat_id, user_id, source_type, source_path, video_path, region_info, report_json, representative_images) "
                "VALUES (NULL, %s, 'pdf', %s, NULL, CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON))",
                (user_id, source_path, "[]", report_payload, "[]"),
            )
            return cursor.lastrowid


def delete_pdf_report_and_refs(report_id: int, user_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        _ensure_chat_report_refs_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM reports WHERE id=%s AND user_id=%s AND source_type='pdf'",
                (report_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return False
            cursor.execute(
                "UPDATE chat_report_refs SET status='removed', updated_at=CURRENT_TIMESTAMP WHERE report_id=%s",
                (report_id,),
            )
            cursor.execute(
                "DELETE FROM reports WHERE id=%s AND user_id=%s AND source_type='pdf'",
                (report_id, user_id),
            )
            return cursor.rowcount > 0

def get_chat_messages(
    chat_id: int, limit: int = 50, offset: int = 0
) -> Optional[List[Dict[str, Any]]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT cd.id AS id, cd.chat_id AS chat_id, cd.role AS role, cd.created_at AS created_at, "
                "m.content AS message_content, m.meta AS message_meta, "
                "r.region_info AS report_region_info, r.report_json AS report_json, "
                "r.video_path AS video_path, r.representative_images AS representative_images "
                "FROM chat_details cd "
                "LEFT JOIN messages m ON cd.message_id = m.id "
                "LEFT JOIN reports r ON cd.report_id = r.id "
                "WHERE cd.chat_id=%s "
                "ORDER BY cd.created_at ASC LIMIT %s OFFSET %s",
                (chat_id, limit, offset),
            )
            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                role = row.get("role")
                if role == "report":
                    content = _safe_parse_json(row.get("report_region_info"))
                    meta = {
                        "type": "region_info",
                        "video_path": row.get("video_path"),
                        "representative_images": _safe_parse_json(row.get("representative_images")),
                        "report": _safe_parse_json(row.get("report_json")),
                    }
                else:
                    content = row.get("message_content") or ""
                    meta = _safe_parse_json(row.get("message_meta"))
                results.append(
                    {
                        "id": row.get("id"),
                        "chat_id": row.get("chat_id"),
                        "role": role,
                        "content": content,
                        "meta": meta,
                        "created_at": row.get("created_at"),
                    }
                )
            return results


def get_recent_chat_messages(chat_id: int, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT cd.id AS id, cd.chat_id AS chat_id, cd.role AS role, cd.created_at AS created_at, "
                "m.content AS message_content, m.meta AS message_meta, "
                "r.region_info AS report_region_info, r.report_json AS report_json, "
                "r.video_path AS video_path, r.representative_images AS representative_images "
                "FROM chat_details cd "
                "LEFT JOIN messages m ON cd.message_id = m.id "
                "LEFT JOIN reports r ON cd.report_id = r.id "
                "WHERE cd.chat_id=%s "
                "ORDER BY cd.created_at DESC LIMIT %s",
                (chat_id, limit),
            )
            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                role = row.get("role")
                if role == "report":
                    content = _safe_parse_json(row.get("report_region_info"))
                    meta = {
                        "type": "region_info",
                        "video_path": row.get("video_path"),
                        "representative_images": _safe_parse_json(row.get("representative_images")),
                        "report": _safe_parse_json(row.get("report_json")),
                    }
                else:
                    content = row.get("message_content") or ""
                    meta = _safe_parse_json(row.get("message_meta"))
                results.append(
                    {
                        "id": row.get("id"),
                        "chat_id": row.get("chat_id"),
                        "role": role,
                        "content": content,
                        "meta": meta,
                        "created_at": row.get("created_at"),
                    }
                )
            return results


def get_recent_user_questions(chat_id: int, limit: int = 20) -> List[str]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT m.content FROM chat_details cd "
                "JOIN messages m ON cd.message_id = m.id "
                "WHERE cd.chat_id=%s AND cd.role='user' "
                "ORDER BY cd.created_at DESC LIMIT %s",
                (chat_id, limit),
            )
            rows = cursor.fetchall()
            if not rows:
                return []
            return [row[0] for row in reversed(rows)]


def get_latest_report_region_info(chat_id: int) -> Optional[List[Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT region_info FROM reports "
                "WHERE chat_id=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            )
            row = cursor.fetchone()
            content = row[0] if row else None
            if not content:
                return None
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                return parsed if isinstance(parsed, list) else None
            except json.JSONDecodeError:
                return None


def _prepare_region_info(region_info):
    if isinstance(region_info, str):
        try:
            json.loads(region_info)
            return region_info
        except json.JSONDecodeError:
            return json.dumps(region_info, ensure_ascii=False)
    return json.dumps(region_info, ensure_ascii=False)


def _ensure_report_table(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "chat_id BIGINT NULL,"
            "user_id BIGINT NULL,"
            "source_type VARCHAR(16) NOT NULL DEFAULT 'video',"
            "source_path TEXT,"
            "video_path TEXT,"
            "region_info JSON NOT NULL,"
            "report_json JSON NULL,"
            "representative_images JSON NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute("SHOW COLUMNS FROM reports")
        columns = {row[0] for row in cursor.fetchall()}
        if "report_json" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN report_json JSON NULL"
            )
        if "representative_images" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN representative_images JSON NULL"
            )
        if "chat_id" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN chat_id BIGINT NULL"
            )
        if "user_id" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN user_id BIGINT NULL"
            )
        if "source_type" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'video'"
            )
        if "source_path" not in columns:
            cursor.execute(
                "ALTER TABLE reports "
                "ADD COLUMN source_path TEXT"
            )


def _ensure_chat_report_refs_table(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS chat_report_refs ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "chat_id BIGINT NOT NULL,"
            "report_id BIGINT NOT NULL,"
            "source_chat_id BIGINT NULL,"
            "status VARCHAR(16) NOT NULL DEFAULT 'active',"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
            "UNIQUE KEY uniq_chat_report (chat_id, report_id),"
            "INDEX idx_chat_report_refs_chat (chat_id),"
            "INDEX idx_chat_report_refs_report (report_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )


def _safe_parse_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def chat_has_report(chat_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM reports WHERE chat_id=%s LIMIT 1",
                (chat_id,),
            )
            return cursor.fetchone() is not None


def store_report(
    region_info,
    video_path,
    report_data: Optional[Dict[str, Any]] = None,
    representative_images: Optional[List[str]] = None,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
):
    if region_info is None:
        return None
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        payload = _prepare_region_info(region_info)
        report_payload = _prepare_region_info(report_data) if report_data is not None else None
        images_payload = (
            _prepare_region_info(representative_images) if representative_images is not None else None
        )
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reports (chat_id, user_id, video_path, region_info, report_json, representative_images) "
                "VALUES (%s, %s, %s, CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON))",
                (chat_id, user_id, video_path, payload, report_payload, images_payload),
            )
            return cursor.lastrowid
    return None


def get_latest_report_assets(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT video_path, representative_images, report_json "
                "FROM reports WHERE chat_id=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "video_path": row.get("video_path"),
                "representative_images": _safe_parse_json(row.get("representative_images")),
                "report_json": _safe_parse_json(row.get("report_json")),
            }
