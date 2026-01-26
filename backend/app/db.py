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
            "last_message_at TIMESTAMP NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS chat_messages ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "chat_id BIGINT NOT NULL,"
            "user_id BIGINT NULL,"
            "role VARCHAR(32) NOT NULL,"
            "content LONGTEXT NOT NULL,"
            "meta JSON NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_chat_messages_chat_id_created (chat_id, created_at)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
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
                "SELECT id, user_id, title, status, last_message_at, created_at, updated_at "
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
                "SELECT id, user_id, title, status, last_message_at, created_at, updated_at "
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
        payload = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages (chat_id, user_id, role, content, meta) "
                "VALUES (%s, %s, %s, %s, %s)",
                (chat_id, user_id, role, content, payload),
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
                "SELECT id, chat_id, user_id, role, content, meta, created_at "
                "FROM chat_messages WHERE chat_id=%s "
                "ORDER BY created_at ASC LIMIT %s OFFSET %s",
                (chat_id, limit, offset),
            )
            return cursor.fetchall()


def get_recent_user_questions(chat_id: int, limit: int = 20) -> List[str]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        _ensure_core_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM chat_messages "
                "WHERE chat_id=%s AND role='user' "
                "ORDER BY created_at DESC LIMIT %s",
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
                "SELECT content FROM chat_messages "
                "WHERE chat_id=%s AND role='report' "
                "ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            )
            row = cursor.fetchone()
            content = row[0] if row else None
            if not content:
                return None
            try:
                parsed = json.loads(content)
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
            "CREATE TABLE IF NOT EXISTS safety_reports_agent ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "video_path TEXT,"
            "region_info JSON NOT NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )


def store_report(region_info, video_path, chat_id: Optional[int] = None, user_id: Optional[int] = None):
    if region_info is None:
        return False
    conn = _get_connection()
    if not conn:
        return False
    with conn:
        _ensure_core_tables(conn)
        _ensure_report_table(conn)
        payload = _prepare_region_info(region_info)
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO safety_reports_agent (video_path, region_info) "
                "VALUES (%s, CAST(%s AS JSON))",
                (video_path, payload),
            )
    return True
