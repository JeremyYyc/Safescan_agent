import json
import os
import hashlib
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import pymysql

from app.env import load_env

load_env()


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
    with conn.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "user_id INT AUTO_INCREMENT PRIMARY KEY,"
            "username VARCHAR(32),"
            "email VARCHAR(128),"
            "avatar VARCHAR(128),"
            "password VARCHAR(32),"
            "create_time DATETIME,"
            "update_time DATETIME"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS chats ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "user_id BIGINT NULL,"
            "title VARCHAR(255),"
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
                "SELECT user_id, username, email, avatar, password, create_time, update_time "
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
                "SELECT user_id, username, email, avatar, password, create_time, update_time "
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
                "SELECT user_id, username, email, avatar, password, create_time, update_time "
                "FROM users WHERE user_id=%s LIMIT 1",
                (user_id,),
            )
            return cursor.fetchone()


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
        with conn.cursor() as cursor:
            password_hash = _hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, email, avatar, password, create_time, update_time) "
                "VALUES (%s, %s, %s, %s, NOW(), NOW())",
                (username, email, "", password_hash),
            )
            user_id = cursor.lastrowid
        return get_user_by_id(user_id)


def verify_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user:
        return None
    password_hash = _hash_password(password)
    if user.get("password") != password_hash:
        return None
    return user


def create_chat(title: Optional[str] = None, user_id: Optional[int] = None) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        _ensure_core_tables(conn)
        if user_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chats (user_id, title, status) VALUES (%s, %s, %s)",
                (user_id, title or "New Chat", "active"),
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
                "SELECT id, user_id, title, status, pinned, last_message_at, created_at, updated_at "
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
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            params: List[Any] = []
            query = (
                "SELECT id, user_id, title, status, pinned, last_message_at, created_at, updated_at "
                "FROM chats"
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
        with conn.cursor() as cursor:
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
            cursor.execute("DELETE FROM reports WHERE chat_id=%s", (chat_id,))
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
