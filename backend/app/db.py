import json
import os
import hashlib
import mimetypes
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

import pymysql

from app.env import load_env
from app.utils.public_ids import (
    KIND_CHAT,
    KIND_REPORT,
    decode_public_id,
    encode_public_id,
)
from app.utils.uuid7 import uuid7_hex

load_env()


_SCHEMA_MIGRATION_LOCK = threading.Lock()


def _to_chat_public_id(chat_uuid: Any, fallback: Optional[Any] = None) -> Optional[str]:
    value = str(chat_uuid or "").strip().lower()
    if len(value) == 32:
        try:
            return encode_public_id(KIND_CHAT, value)
        except Exception:
            pass
    if fallback is None:
        return None
    return str(fallback)


def _to_report_public_id(report_uuid: Any, fallback: Optional[Any] = None) -> Optional[str]:
    value = str(report_uuid or "").strip().lower()
    if len(value) == 32:
        try:
            return encode_public_id(KIND_REPORT, value)
        except Exception:
            pass
    if fallback is None:
        return None
    return str(fallback)


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
                "chat_uuid CHAR(32) NULL,"
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
            if "chat_uuid" not in columns:
                try:
                    cursor.execute(
                        "ALTER TABLE chats "
                        "ADD COLUMN chat_uuid CHAR(32) NULL"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1060):
                        raise

            cursor.execute("SELECT id FROM chats WHERE chat_uuid IS NULL OR chat_uuid=''")
            pending_chat_ids = [row[0] for row in cursor.fetchall()]
            for chat_id in pending_chat_ids:
                cursor.execute(
                    "UPDATE chats SET chat_uuid=%s WHERE id=%s",
                    (uuid7_hex(), chat_id),
                )

            cursor.execute(
                "SELECT chat_uuid FROM chats "
                "WHERE chat_uuid IS NOT NULL AND chat_uuid<>'' "
                "GROUP BY chat_uuid HAVING COUNT(*) > 1"
            )
            duplicate_chat_uuids = [row[0] for row in cursor.fetchall()]
            for dup_uuid in duplicate_chat_uuids:
                cursor.execute(
                    "SELECT id FROM chats WHERE chat_uuid=%s ORDER BY id ASC",
                    (dup_uuid,),
                )
                dup_chat_ids = [row[0] for row in cursor.fetchall()]
                for chat_id in dup_chat_ids[1:]:
                    cursor.execute(
                        "UPDATE chats SET chat_uuid=%s WHERE id=%s",
                        (uuid7_hex(), chat_id),
                    )

            cursor.execute("SHOW INDEX FROM chats")
            chat_indexes = {row[2] for row in cursor.fetchall()}
            if "uniq_chats_chat_uuid" not in chat_indexes:
                try:
                    cursor.execute(
                        "ALTER TABLE chats "
                        "ADD UNIQUE KEY uniq_chats_chat_uuid (chat_uuid)"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1061):
                        raise

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
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    chat_uuid = uuid7_hex()
                    cursor.execute(
                        "INSERT INTO chats (chat_uuid, user_id, title, status, chat_type) VALUES (%s, %s, %s, %s, %s)",
                        (chat_uuid, user_id, title or "New Chat", "active", chat_type),
                    )
                    return cursor.lastrowid
            except pymysql.IntegrityError:
                continue
    return None


def _normalize_chat_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    normalized = dict(row)
    internal_id = normalized.get("id")
    chat_uuid = str(normalized.get("chat_uuid") or "").strip()
    public_id = _to_chat_public_id(chat_uuid, fallback=internal_id)
    normalized["id"] = public_id
    normalized["chat_id"] = public_id
    normalized["chat_uuid"] = public_id
    return normalized


def get_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, chat_uuid, user_id, title, status, pinned, chat_type, last_message_at, created_at, updated_at "
                "FROM chats WHERE id=%s",
                (chat_id,),
            )
            row = cursor.fetchone()
            return _normalize_chat_row(row)


def get_chat_by_public_id(chat_ref: Any) -> Optional[Dict[str, Any]]:
    value = str(chat_ref or "").strip()
    if not value:
        return None
    decoded = decode_public_id(value, expected_kind=KIND_CHAT)
    if decoded:
        value = decoded["uuid_hex"]
    if value.isdigit():
        chat = get_chat(int(value))
        if chat:
            return chat
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, chat_uuid, user_id, title, status, pinned, chat_type, last_message_at, created_at, updated_at "
                "FROM chats WHERE chat_uuid=%s LIMIT 1",
                (value,),
            )
            row = cursor.fetchone()
            return _normalize_chat_row(row)


def resolve_chat_internal_id(chat_ref: Any) -> Optional[int]:
    value = str(chat_ref or "").strip()
    if not value:
        return None
    decoded = decode_public_id(value, expected_kind=KIND_CHAT)
    if decoded:
        value = decoded["uuid_hex"]
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            if value.isdigit():
                cursor.execute("SELECT id FROM chats WHERE id=%s LIMIT 1", (int(value),))
                row = cursor.fetchone()
                return int(row[0]) if row else None
            cursor.execute("SELECT id FROM chats WHERE chat_uuid=%s LIMIT 1", (value,))
            row = cursor.fetchone()
            return int(row[0]) if row else None


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
                "c.id, c.chat_uuid, c.user_id, c.title, c.status, c.pinned, c.chat_type, "
                "c.last_message_at, c.created_at, c.updated_at, "
                "EXISTS(SELECT 1 FROM reports r "
                "WHERE r.origin_chat_id=c.id "
                "AND r.report_kind='analysis') AS has_report "
                "FROM chats c"
            )
            if user_id is None:
                return []
            query += " WHERE user_id=%s"
            params.append(user_id)
            query += " ORDER BY COALESCE(last_message_at, updated_at) DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []
            return [_normalize_chat_row(row) for row in rows if row]


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
                "SELECT id FROM reports WHERE origin_chat_id=%s",
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
                    f"DELETE FROM report_assets WHERE report_id IN ({placeholders})",
                    tuple(report_ids),
                )
                cursor.execute(
                    f"DELETE FROM report_pdf WHERE report_id IN ({placeholders})",
                    tuple(report_ids),
                )
                cursor.execute(
                    f"DELETE FROM report_analysis WHERE report_id IN ({placeholders})",
                    tuple(report_ids),
                )
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


def list_chat_report_refs_enriched(chat_id: int) -> List[Dict[str, Any]]:
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
            refs = cursor.fetchall() or []
        report_ids = [int(ref["report_id"]) for ref in refs if ref.get("report_id") is not None]
        reports_map = _get_reports_by_ids_with_conn(conn, report_ids)
        source_chat_ids: List[int] = []
        for ref in refs:
            source_chat_id = ref.get("source_chat_id")
            if source_chat_id is not None:
                source_chat_ids.append(int(source_chat_id))
                continue
            report = reports_map.get(int(ref["report_id"])) if ref.get("report_id") is not None else None
            if report and report.get("origin_chat_id") is not None:
                source_chat_ids.append(int(report["origin_chat_id"]))
        chat_briefs = _get_chat_briefs_by_internal_ids(conn, source_chat_ids)
        results: List[Dict[str, Any]] = []
        for ref in refs:
            report_id = ref.get("report_id")
            report = reports_map.get(int(report_id)) if report_id is not None else None
            source_chat_id = ref.get("source_chat_id")
            if source_chat_id is None and report and report.get("origin_chat_id") is not None:
                source_chat_id = int(report["origin_chat_id"])
            source_chat = chat_briefs.get(int(source_chat_id)) if source_chat_id is not None else None
            results.append(
                {
                    "id": ref.get("id"),
                    "chat_id": ref.get("chat_id"),
                    "report_id": report_id,
                    "status": ref.get("status"),
                    "created_at": ref.get("created_at"),
                    "updated_at": ref.get("updated_at"),
                    "source_chat_internal_id": source_chat_id,
                    "source_chat_id": source_chat.get("id") if source_chat else None,
                    "source_chat_title": source_chat.get("title") if source_chat else None,
                    "report": report,
                }
            )
        return results


def _normalize_storage_path(path: Any) -> str:
    return str(path or "").strip().replace("\\", "/")


def _storage_path_hash(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _load_files_by_ids(conn, file_ids: List[int]) -> Dict[int, str]:
    if not file_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(file_ids))
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            f"SELECT id, storage_path FROM files WHERE id IN ({placeholders})",
            tuple(file_ids),
        )
        rows = cursor.fetchall() or []
    result: Dict[int, str] = {}
    for row in rows:
        file_id = row.get("id")
        if file_id is None:
            continue
        result[int(file_id)] = row.get("storage_path") or ""
    return result


def _load_report_asset_images(conn, report_ids: List[int]) -> Dict[int, List[str]]:
    if not report_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(report_ids))
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT ra.report_id AS report_id, f.storage_path AS storage_path "
            "FROM report_assets ra "
            "JOIN files f ON f.id=ra.file_id "
            f"WHERE ra.asset_kind='representative_image' AND ra.report_id IN ({placeholders}) "
            "ORDER BY ra.report_id ASC, ra.sort_order ASC, ra.id ASC",
            tuple(report_ids),
        )
        rows = cursor.fetchall() or []
    result: Dict[int, List[str]] = {}
    for row in rows:
        report_id = row.get("report_id")
        if report_id is None:
            continue
        result.setdefault(int(report_id), []).append(row.get("storage_path") or "")
    return result


def _resolve_report_kind(row: Dict[str, Any]) -> str:
    report_kind = str(row.get("report_kind") or "").strip().lower()
    if report_kind in ("analysis", "pdf"):
        return report_kind
    return "analysis"


def _normalize_report_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    normalized = dict(row)
    report_pk = normalized.get("id")
    report_uuid_raw = normalized.get("report_uuid")
    public_report_id = _to_report_public_id(report_uuid_raw, fallback=report_pk)
    normalized["report_id"] = public_report_id
    normalized["report_uuid"] = public_report_id
    normalized["report_kind"] = _resolve_report_kind(normalized)
    if normalized.get("source_type") not in ("pdf", "video"):
        normalized["source_type"] = "pdf" if normalized["report_kind"] == "pdf" else "video"
    origin_chat_id = normalized.get("origin_chat_id")
    if origin_chat_id is None:
        origin_chat_id = normalized.get("chat_id")
    normalized["chat_id"] = origin_chat_id
    normalized["origin_chat_id"] = origin_chat_id
    normalized["region_info"] = _safe_parse_json(normalized.get("region_info"))
    normalized["report_json"] = _safe_parse_json(normalized.get("report_json"))
    normalized["representative_images"] = _safe_parse_json(normalized.get("representative_images"))
    return normalized


def _fetch_reports_enriched(
    conn,
    where_clause: str,
    params: Tuple[Any, ...],
    order_clause: str = "",
    limit_clause: str = "",
) -> List[Dict[str, Any]]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT "
            "r.id AS id, r.report_uuid AS report_uuid, r.user_id AS user_id, "
            "r.report_kind AS report_kind, r.origin_chat_id AS origin_chat_id, r.title AS title, r.status AS status, "
            "r.created_at AS created_at, "
            "ra.video_file_id AS video_file_id, ra.region_info_json AS analysis_region_info, ra.report_json AS analysis_report_json, "
            "rp.file_id AS pdf_file_id, rp.pdf_kind AS pdf_kind, rp.derived_from_report_id AS derived_from_report_id, "
            "rp.content_preview AS content_preview "
            "FROM reports r "
            "LEFT JOIN report_analysis ra ON ra.report_id=r.id "
            "LEFT JOIN report_pdf rp ON rp.report_id=r.id "
            f"{where_clause} {order_clause} {limit_clause}",
            params,
        )
        rows = cursor.fetchall() or []

    file_ids: List[int] = []
    report_ids: List[int] = []
    for row in rows:
        report_id = row.get("id")
        if report_id is not None:
            report_ids.append(int(report_id))
        for file_key in ("video_file_id", "pdf_file_id"):
            file_value = row.get(file_key)
            if file_value is not None:
                file_ids.append(int(file_value))
    files_map = _load_files_by_ids(conn, list({value for value in file_ids}))
    images_map = _load_report_asset_images(conn, list({value for value in report_ids}))

    result: List[Dict[str, Any]] = []
    for row in rows:
        report_id = int(row["id"])
        report_kind = _resolve_report_kind({"report_kind": row.get("report_kind")})
        source_type = "pdf" if report_kind == "pdf" else "video"
        source_path = files_map.get(int(row["pdf_file_id"])) if row.get("pdf_file_id") is not None else None
        video_path = files_map.get(int(row["video_file_id"])) if row.get("video_file_id") is not None else None
        region_info = row.get("analysis_region_info") if report_kind == "analysis" else []
        if region_info is None:
            region_info = []
        report_json = row.get("analysis_report_json")
        if report_kind == "pdf":
            report_json = {
                "title": row.get("title") or "",
                "source_type": "pdf",
                "summary": "",
                "content_preview": row.get("content_preview") or "",
            }
        elif report_json is None:
            report_json = {}
        representative_images = images_map.get(report_id) or []

        origin_chat_id = row.get("origin_chat_id")
        title = str(row.get("title") or "").strip()
        if not title:
            report_payload = _safe_parse_json(report_json)
            if isinstance(report_payload, dict):
                title = str(report_payload.get("title") or "").strip()

        normalized = _normalize_report_row(
            {
                "id": report_id,
                "report_uuid": row.get("report_uuid"),
                "chat_id": origin_chat_id,
                "origin_chat_id": origin_chat_id,
                "user_id": row.get("user_id"),
                "source_type": source_type,
                "source_path": source_path,
                "video_path": video_path,
                "region_info": region_info,
                "report_json": report_json,
                "representative_images": representative_images or [],
                "created_at": row.get("created_at"),
                "report_kind": report_kind,
                "title": title,
                "status": row.get("status") or "active",
                "pdf_kind": row.get("pdf_kind"),
                "derived_from_report_id": row.get("derived_from_report_id"),
                "content_preview": row.get("content_preview"),
            }
        )
        if normalized:
            result.append(normalized)
    return result


def _get_report_by_id_with_conn(conn, report_id: int) -> Optional[Dict[str, Any]]:
    rows = _fetch_reports_enriched(
        conn,
        "WHERE r.id=%s",
        (report_id,),
        limit_clause="LIMIT 1",
    )
    return rows[0] if rows else None


def _get_reports_by_ids_with_conn(conn, report_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    unique_ids = sorted({int(item) for item in report_ids if item is not None})
    if not unique_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(unique_ids))
    rows = _fetch_reports_enriched(
        conn,
        f"WHERE r.id IN ({placeholders})",
        tuple(unique_ids),
    )
    return {int(row["id"]): row for row in rows if row and row.get("id") is not None}


def _get_chat_public_ids_by_internal_ids(conn, chat_ids: List[int]) -> Dict[int, str]:
    unique_ids = sorted({int(item) for item in chat_ids if item is not None})
    if not unique_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(unique_ids))
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, chat_uuid FROM chats "
            f"WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        rows = cursor.fetchall() or []
    result: Dict[int, str] = {}
    for row in rows:
        chat_id = row.get("id")
        if chat_id is None:
            continue
        result[int(chat_id)] = _to_chat_public_id(row.get("chat_uuid"), fallback=chat_id)
    return result


def _get_chat_briefs_by_internal_ids(conn, chat_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    unique_ids = sorted({int(item) for item in chat_ids if item is not None})
    if not unique_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(unique_ids))
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, chat_uuid, title FROM chats "
            f"WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        rows = cursor.fetchall() or []
    result: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        chat_id = row.get("id")
        if chat_id is None:
            continue
        result[int(chat_id)] = {
            "id": _to_chat_public_id(row.get("chat_uuid"), fallback=chat_id),
            "title": row.get("title"),
        }
    return result


def _upsert_file_record(conn, user_id: Optional[int], raw_path: Any) -> Optional[int]:
    normalized_path = _normalize_storage_path(raw_path)
    if not normalized_path:
        return None
    path_hash = _storage_path_hash(normalized_path)
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, storage_path FROM files WHERE storage_path_hash=%s LIMIT 1",
            (path_hash,),
        )
        row = cursor.fetchone()
        if row and _normalize_storage_path(row.get("storage_path")) == normalized_path:
            return int(row["id"])
        cursor.execute(
            "SELECT id FROM files WHERE storage_path=%s LIMIT 1",
            (normalized_path,),
        )
        exact_row = cursor.fetchone()
        if exact_row and exact_row.get("id") is not None:
            return int(exact_row["id"])

        resolved_size = None
        candidate = os.path.abspath(normalized_path)
        if os.path.isfile(candidate):
            try:
                resolved_size = os.path.getsize(candidate)
            except OSError:
                resolved_size = None
        mime_type, _ = mimetypes.guess_type(normalized_path)
        file_ext = os.path.splitext(normalized_path)[1].lower()[:16] or None
        for _ in range(5):
            try:
                cursor.execute(
                    "INSERT INTO files (file_uuid, user_id, storage_path, storage_path_hash, mime_type, file_ext, file_size, sha256) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)",
                    (
                        uuid7_hex(),
                        int(user_id) if user_id is not None else None,
                        normalized_path,
                        path_hash,
                        mime_type,
                        file_ext,
                        resolved_size,
                    ),
                )
                return int(cursor.lastrowid)
            except pymysql.IntegrityError:
                cursor.execute(
                    "SELECT id, storage_path FROM files WHERE storage_path_hash=%s LIMIT 1",
                    (path_hash,),
                )
                retried = cursor.fetchone()
                if retried and _normalize_storage_path(retried.get("storage_path")) == normalized_path:
                    return int(retried["id"])
                cursor.execute(
                    "SELECT id FROM files WHERE storage_path=%s LIMIT 1",
                    (normalized_path,),
                )
                retried_exact = cursor.fetchone()
                if retried_exact and retried_exact.get("id") is not None:
                    return int(retried_exact["id"])
                continue
    return None


def _replace_report_assets(
    conn,
    report_id: int,
    user_id: Optional[int],
    representative_images: Optional[List[str]],
) -> None:
    images = representative_images or []
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM report_assets WHERE report_id=%s AND asset_kind='representative_image'",
            (report_id,),
        )
    for idx, image_path in enumerate(images):
        file_id = _upsert_file_record(conn, user_id, image_path)
        if file_id is None:
            continue
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO report_assets (report_id, file_id, asset_kind, sort_order) "
                "VALUES (%s, %s, 'representative_image', %s) "
                "ON DUPLICATE KEY UPDATE sort_order=VALUES(sort_order)",
                (report_id, file_id, idx),
            )


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
                "SELECT report_id, source_chat_id, created_at "
                "FROM chat_report_refs "
                "WHERE chat_id=%s AND status='active' "
                "ORDER BY created_at ASC",
                (chat_id,),
            )
            refs = cursor.fetchall() or []
        report_ids = [int(ref["report_id"]) for ref in refs if ref.get("report_id") is not None]
        reports_map = _get_reports_by_ids_with_conn(conn, report_ids)
        source_chat_ids = [
            int(ref["source_chat_id"])
            for ref in refs
            if ref.get("source_chat_id") is not None
        ]
        source_chat_public_ids = _get_chat_public_ids_by_internal_ids(conn, source_chat_ids)
        results: List[Dict[str, Any]] = []
        for ref in refs:
            report_pk = ref.get("report_id")
            if report_pk is None:
                continue
            report = reports_map.get(int(report_pk))
            if not report:
                continue
            source_chat_id_raw = ref.get("source_chat_id")
            source_chat_id = int(source_chat_id_raw) if source_chat_id_raw is not None else report.get("origin_chat_id")
            source_chat_public_id = (
                source_chat_public_ids.get(int(source_chat_id))
                if source_chat_id is not None
                else None
            )
            results.append(
                {
                    "report_pk": report.get("id"),
                    "report_id": report.get("report_id"),
                    "report_uuid": report.get("report_uuid"),
                    "source_chat_id": source_chat_public_id or str(source_chat_id) if source_chat_id is not None else None,
                    "user_id": report.get("user_id"),
                    "source_type": report.get("source_type"),
                    "source_path": report.get("source_path"),
                    "video_path": report.get("video_path"),
                    "region_info": report.get("region_info"),
                    "report_json": report.get("report_json"),
                    "representative_images": report.get("representative_images"),
                    "created_at": ref.get("created_at"),
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
                "SELECT id FROM reports "
                "WHERE origin_chat_id=%s "
                "AND report_kind='analysis' "
                "ORDER BY created_at DESC LIMIT 1",
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
                "SELECT cr.report_id AS report_id "
                "FROM chat_report_refs cr "
                "JOIN reports r ON cr.report_id=r.id "
                "WHERE cr.chat_id=%s AND cr.status='active' AND cr.source_chat_id=%s "
                "AND r.report_kind='pdf' "
                "ORDER BY r.created_at DESC LIMIT 1",
                (chat_id, chat_id),
            )
            row = cursor.fetchone()
        if not row or row.get("report_id") is None:
            return None
        report = _get_report_by_id_with_conn(conn, int(row["report_id"]))
        if not report:
            return None
        return {
            "report_id": report.get("id"),
            "source_path": report.get("source_path"),
            "report_json": report.get("report_json"),
            "created_at": report.get("created_at"),
        }


def get_report(report_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        return _get_report_by_id_with_conn(conn, report_id)


def get_report_by_public_id(report_ref: Any) -> Optional[Dict[str, Any]]:
    value = str(report_ref or "").strip()
    if not value:
        return None
    decoded = decode_public_id(value, expected_kind=KIND_REPORT)
    if decoded:
        value = decoded["uuid_hex"]
    if value.isdigit():
        report = get_report(int(value))
        if report:
            return report
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        rows = _fetch_reports_enriched(
            conn,
            "WHERE r.report_uuid=%s",
            (value,),
            limit_clause="LIMIT 1",
        )
        return rows[0] if rows else None


def resolve_report_internal_id(report_ref: Any) -> Optional[int]:
    value = str(report_ref or "").strip()
    if not value:
        return None
    decoded = decode_public_id(value, expected_kind=KIND_REPORT)
    if decoded:
        value = decoded["uuid_hex"]
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        with conn.cursor() as cursor:
            if value.isdigit():
                cursor.execute("SELECT id FROM reports WHERE id=%s LIMIT 1", (int(value),))
                row = cursor.fetchone()
                return int(row[0]) if row else None
            cursor.execute("SELECT id FROM reports WHERE report_uuid=%s LIMIT 1", (value,))
            row = cursor.fetchone()
            return int(row[0]) if row else None


def list_reports_by_chat(chat_id: int) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        rows = _fetch_reports_enriched(
            conn,
            "WHERE r.origin_chat_id=%s",
            (chat_id,),
            order_clause="ORDER BY r.created_at ASC",
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "id": row.get("id"),
                    "report_uuid": row.get("report_uuid"),
                    "report_id": row.get("report_id"),
                    "chat_id": row.get("chat_id"),
                    "user_id": row.get("user_id"),
                    "source_type": row.get("source_type"),
                    "source_path": row.get("source_path"),
                    "video_path": row.get("video_path"),
                    "region_info": row.get("region_info"),
                    "report_json": row.get("report_json"),
                    "representative_images": row.get("representative_images"),
                    "created_at": row.get("created_at"),
                }
            )
        return results


def count_reports_referencing_fragment(fragment: str) -> int:
    target = str(fragment or "").strip().lower().replace("\\", "/")
    if not target:
        return 0
    conn = _get_connection()
    if not conn:
        return 0
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        pattern = f"%{target}%"
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM files "
                "WHERE LOWER(REPLACE(COALESCE(storage_path, ''), '\\\\', '/')) LIKE %s",
                (pattern,),
            )
            files_row = cursor.fetchone()
            files_count = int(files_row[0] if files_row else 0)
            cursor.execute(
                "SELECT COUNT(*) FROM report_analysis "
                "WHERE LOWER(REPLACE(COALESCE(CAST(region_info_json AS CHAR), ''), '\\\\', '/')) LIKE %s "
                "OR LOWER(REPLACE(COALESCE(CAST(report_json AS CHAR), ''), '\\\\', '/')) LIKE %s",
                (pattern, pattern),
            )
            analysis_row = cursor.fetchone()
            analysis_count = int(analysis_row[0] if analysis_row else 0)
            cursor.execute(
                "SELECT COUNT(*) FROM report_pdf "
                "WHERE LOWER(REPLACE(COALESCE(content_preview, ''), '\\\\', '/')) LIKE %s",
                (pattern,),
            )
            pdf_row = cursor.fetchone()
            pdf_count = int(pdf_row[0] if pdf_row else 0)
            return files_count + analysis_count + pdf_count


def store_pdf_report(
    *,
    user_id: int,
    source_path: str,
    title: str,
    extracted_text: str = "",
    origin_chat_id: Optional[int] = None,
    pdf_kind: str = "uploaded",
    derived_from_report_id: Optional[int] = None,
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        safe_title = (title or "Uploaded PDF Report").strip()[:255] or "Uploaded PDF Report"
        preview_text = (extracted_text or "").strip()[:8000]
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    report_uuid = uuid7_hex()
                    cursor.execute(
                        "INSERT INTO reports (report_uuid, user_id, report_kind, origin_chat_id, title, status) "
                        "VALUES (%s, %s, 'pdf', %s, %s, 'active')",
                        (report_uuid, user_id, origin_chat_id, safe_title),
                    )
                    report_id = int(cursor.lastrowid)
                    file_id = _upsert_file_record(conn, user_id, source_path)
                    if file_id is not None:
                        normalized_kind = str(pdf_kind or "uploaded").strip().lower()
                        if normalized_kind not in ("uploaded", "exported"):
                            normalized_kind = "uploaded"
                        cursor.execute(
                            "INSERT INTO report_pdf (report_id, file_id, pdf_kind, derived_from_report_id, content_preview) "
                            "VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE "
                            "file_id=VALUES(file_id), "
                            "pdf_kind=VALUES(pdf_kind), "
                            "derived_from_report_id=VALUES(derived_from_report_id), "
                            "content_preview=VALUES(content_preview)",
                            (report_id, file_id, normalized_kind, derived_from_report_id, preview_text),
                        )
                    return report_id
            except pymysql.IntegrityError:
                continue
    return None


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
                "SELECT id FROM reports "
                "WHERE id=%s AND user_id=%s "
                "AND report_kind='pdf'",
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
                "DELETE FROM report_assets WHERE report_id=%s",
                (report_id,),
            )
            cursor.execute(
                "DELETE FROM report_pdf WHERE report_id=%s",
                (report_id,),
            )
            cursor.execute(
                "DELETE FROM report_analysis WHERE report_id=%s",
                (report_id,),
            )
            cursor.execute(
                "DELETE FROM reports "
                "WHERE id=%s AND user_id=%s "
                "AND report_kind='pdf'",
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
        _ensure_report_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT cd.id AS id, cd.chat_id AS chat_id, cd.role AS role, cd.created_at AS created_at, "
                "m.content AS message_content, m.meta AS message_meta, "
                "cd.report_id AS report_id "
                "FROM chat_details cd "
                "LEFT JOIN messages m ON cd.message_id = m.id "
                "WHERE cd.chat_id=%s "
                "ORDER BY cd.created_at ASC LIMIT %s OFFSET %s",
                (chat_id, limit, offset),
            )
            rows = cursor.fetchall()
            report_ids = [
                int(row["report_id"])
                for row in rows
                if row.get("role") == "report" and row.get("report_id") is not None
            ]
            reports_map = _get_reports_by_ids_with_conn(conn, report_ids)
            results: List[Dict[str, Any]] = []
            for row in rows:
                role = row.get("role")
                if role == "report":
                    report_id = row.get("report_id")
                    report = reports_map.get(int(report_id)) if report_id is not None else None
                    content = report.get("region_info") if report else None
                    meta = {
                        "type": "region_info",
                        "video_path": report.get("video_path") if report else None,
                        "representative_images": report.get("representative_images") if report else None,
                        "report": report.get("report_json") if report else None,
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
        _ensure_report_table(conn)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT cd.id AS id, cd.chat_id AS chat_id, cd.role AS role, cd.created_at AS created_at, "
                "m.content AS message_content, m.meta AS message_meta, "
                "cd.report_id AS report_id "
                "FROM chat_details cd "
                "LEFT JOIN messages m ON cd.message_id = m.id "
                "WHERE cd.chat_id=%s "
                "ORDER BY cd.created_at DESC LIMIT %s",
                (chat_id, limit),
            )
            rows = cursor.fetchall()
            report_ids = [
                int(row["report_id"])
                for row in rows
                if row.get("role") == "report" and row.get("report_id") is not None
            ]
            reports_map = _get_reports_by_ids_with_conn(conn, report_ids)
            results: List[Dict[str, Any]] = []
            for row in rows:
                role = row.get("role")
                if role == "report":
                    report_id = row.get("report_id")
                    report = reports_map.get(int(report_id)) if report_id is not None else None
                    content = report.get("region_info") if report else None
                    meta = {
                        "type": "region_info",
                        "video_path": report.get("video_path") if report else None,
                        "representative_images": report.get("representative_images") if report else None,
                        "report": report.get("report_json") if report else None,
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
        _ensure_report_table(conn)
        rows = _fetch_reports_enriched(
            conn,
            "WHERE r.origin_chat_id=%s AND r.report_kind='analysis'",
            (chat_id,),
            order_clause="ORDER BY r.created_at DESC",
            limit_clause="LIMIT 1",
        )
        if not rows:
            return None
        region_info = rows[0].get("region_info")
        return region_info if isinstance(region_info, list) else None


def _prepare_region_info(region_info):
    if isinstance(region_info, str):
        try:
            json.loads(region_info)
            return region_info
        except json.JSONDecodeError:
            return json.dumps(region_info, ensure_ascii=False)
    return json.dumps(region_info, ensure_ascii=False)


def _ensure_report_table(conn) -> None:
    with _SCHEMA_MIGRATION_LOCK:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS reports ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "user_id BIGINT NULL,"
                "report_kind VARCHAR(16) NOT NULL DEFAULT 'analysis',"
                "origin_chat_id BIGINT NULL,"
                "title VARCHAR(255) NULL,"
                "status VARCHAR(16) NOT NULL DEFAULT 'active',"
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )
            cursor.execute("SHOW COLUMNS FROM reports")
            columns = {row[0] for row in cursor.fetchall()}
            if "user_id" not in columns:
                cursor.execute(
                    "ALTER TABLE reports "
                    "ADD COLUMN user_id BIGINT NULL"
                )
            if "report_kind" not in columns:
                cursor.execute(
                    "ALTER TABLE reports "
                    "ADD COLUMN report_kind VARCHAR(16) NOT NULL DEFAULT 'analysis'"
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
            if "chat_id" in columns:
                cursor.execute(
                    "UPDATE reports SET origin_chat_id=chat_id "
                    "WHERE origin_chat_id IS NULL AND chat_id IS NOT NULL"
                )
            if "source_type" in columns:
                cursor.execute(
                    "UPDATE reports "
                    "SET report_kind=CASE WHEN COALESCE(source_type, 'video')='pdf' THEN 'pdf' ELSE 'analysis' END "
                    "WHERE report_kind IS NULL OR report_kind=''"
                )
            else:
                cursor.execute(
                    "UPDATE reports SET report_kind='analysis' "
                    "WHERE report_kind IS NULL OR report_kind=''"
                )
            cursor.execute(
                "UPDATE reports SET status='active' "
                "WHERE status IS NULL OR status=''"
            )
            cursor.execute(
                "ALTER TABLE reports "
                "MODIFY COLUMN report_kind VARCHAR(16) NOT NULL DEFAULT 'analysis'"
            )
            cursor.execute(
                "ALTER TABLE reports "
                "MODIFY COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"
            )
            if "report_uuid" not in columns:
                try:
                    cursor.execute(
                        "ALTER TABLE reports "
                        "ADD COLUMN report_uuid CHAR(32) NULL"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1060):
                        raise

            cursor.execute("SELECT id FROM reports WHERE report_uuid IS NULL OR report_uuid=''")
            pending_report_ids = [row[0] for row in cursor.fetchall()]
            for report_id in pending_report_ids:
                cursor.execute(
                    "UPDATE reports SET report_uuid=%s WHERE id=%s",
                    (uuid7_hex(), report_id),
                )

            cursor.execute(
                "SELECT report_uuid FROM reports "
                "WHERE report_uuid IS NOT NULL AND report_uuid<>'' "
                "GROUP BY report_uuid HAVING COUNT(*) > 1"
            )
            duplicate_values = [row[0] for row in cursor.fetchall()]
            for dup_uuid in duplicate_values:
                cursor.execute(
                    "SELECT id FROM reports WHERE report_uuid=%s ORDER BY id ASC",
                    (dup_uuid,),
                )
                dup_report_ids = [row[0] for row in cursor.fetchall()]
                for report_id in dup_report_ids[1:]:
                    cursor.execute(
                        "UPDATE reports SET report_uuid=%s WHERE id=%s",
                        (uuid7_hex(), report_id),
                    )

            cursor.execute("SHOW INDEX FROM reports")
            report_indexes = {row[2] for row in cursor.fetchall()}
            if "uniq_reports_report_uuid" not in report_indexes:
                try:
                    cursor.execute(
                        "ALTER TABLE reports "
                        "ADD UNIQUE KEY uniq_reports_report_uuid (report_uuid)"
                    )
                except Exception as exc:
                    if not _is_mysql_operational_error(exc, 1061):
                        raise
            if "idx_reports_kind" not in report_indexes:
                cursor.execute(
                    "ALTER TABLE reports "
                    "ADD INDEX idx_reports_kind (report_kind)"
                )
            if "idx_reports_origin_chat" not in report_indexes:
                cursor.execute(
                    "ALTER TABLE reports "
                    "ADD INDEX idx_reports_origin_chat (origin_chat_id)"
                )

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
            for file_id, storage_path in pending_file_rows:
                normalized_path = _normalize_storage_path(storage_path)
                cursor.execute(
                    "UPDATE files SET storage_path_hash=%s WHERE id=%s",
                    (_storage_path_hash(normalized_path), file_id),
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
                "SELECT 1 FROM reports "
                "WHERE origin_chat_id=%s AND report_kind='analysis' "
                "LIMIT 1",
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
        normalized_title = ""
        if isinstance(report_data, dict):
            normalized_title = str(report_data.get("title") or "").strip()
        if not normalized_title:
            normalized_title = f"Report {chat_id}" if chat_id is not None else "Analysis Report"
        normalized_images = representative_images or []
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    report_uuid = uuid7_hex()
                    cursor.execute(
                        "INSERT INTO reports (report_uuid, user_id, report_kind, origin_chat_id, title, status) "
                        "VALUES (%s, %s, 'analysis', %s, %s, 'active')",
                        (report_uuid, user_id, chat_id, normalized_title[:255]),
                    )
                    report_id = int(cursor.lastrowid)
                    video_file_id = _upsert_file_record(conn, user_id, video_path)
                    cursor.execute(
                        "INSERT INTO report_analysis (report_id, video_file_id, region_info_json, report_json) "
                        "VALUES (%s, %s, CAST(%s AS JSON), CAST(%s AS JSON)) "
                        "ON DUPLICATE KEY UPDATE "
                        "video_file_id=VALUES(video_file_id), "
                        "region_info_json=VALUES(region_info_json), "
                        "report_json=VALUES(report_json)",
                        (report_id, video_file_id, payload, report_payload),
                    )
                    _replace_report_assets(conn, report_id, user_id, normalized_images)
                    return report_id
            except pymysql.IntegrityError:
                continue
    return None


def get_latest_report_assets(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        rows = _fetch_reports_enriched(
            conn,
            "WHERE r.origin_chat_id=%s AND r.report_kind='analysis'",
            (chat_id,),
            order_clause="ORDER BY r.created_at DESC",
            limit_clause="LIMIT 1",
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "video_path": row.get("video_path"),
            "representative_images": row.get("representative_images"),
            "report_json": row.get("report_json"),
        }
