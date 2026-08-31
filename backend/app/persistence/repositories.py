import json
from app.settings import get_settings
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from app.persistence.database import get_connection as _get_connection, get_engine

from app.utils.public_ids import (
    KIND_CHAT,
    KIND_REPORT,
    decode_public_id,
    encode_public_id,
)
from app.utils.uuid7 import uuid7_hex





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


def is_db_available() -> bool:
    with get_engine().connect() as conn:
        return conn.exec_driver_sql('SELECT 1').scalar_one() == 1


def _get_id(row, key: str = "id"):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[0]


def _hash_password(password: str) -> str:
    import secrets
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt$16384$8$1${salt}${value}"


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    email = email.strip().lower()
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        with conn.cursor(True) as cursor:
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
        with conn.cursor(True) as cursor:
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
        with conn.cursor(True) as cursor:
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
        with conn.cursor(True) as cursor:
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
                        "UPDATE users SET storage_uuid=%s WHERE user_id=%s AND storage_uuid IS NULL",
                        (candidate, user_id),
                    )
                    if cursor.rowcount > 0:
                        return candidate
            except IntegrityError:
                raise

            with conn.cursor(True) as cursor:
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
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET username=%s, update_time=NOW() WHERE user_id=%s",
                (username, user_id),
            )
            return cursor.rowcount >= 0


def create_user(email: str, username: str, password: str) -> Optional[Dict[str, Any]]:
    email = email.strip().lower()
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        password_hash = _hash_password(password)
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    storage_uuid = uuid7_hex()
                    cursor.execute(
                        'INSERT INTO users (username, email, avatar, password, storage_uuid, create_time, update_time) VALUES (%s, %s, %s, %s, %s, NOW(), NOW()) RETURNING user_id',
                        (username, email, "", password_hash, storage_uuid),
                    )
                    user_id = cursor.lastrowid
                    return get_user_by_id(user_id)
            except IntegrityError:
                raise
    return None


def verify_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user:
        return None
    import hmac
    try:
        kind, n, r, p, salt, expected = user["password"].split("$")
        if kind != "scrypt": return None
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)).hex()
        return user if hmac.compare_digest(actual, expected) else None
    except (ValueError, KeyError):
        return None


def create_chat(
    title: Optional[str] = None,
    user_id: Optional[int] = None,
    chat_type: str = "report",
) -> Optional[int]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        if user_id is None:
            return None
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    chat_uuid = uuid7_hex()
                    cursor.execute(
                        'INSERT INTO chats (chat_uuid, user_id, title, status, chat_type) VALUES (%s, %s, %s, %s, %s) RETURNING id',
                        (chat_uuid, user_id, title or "New Chat", "active", chat_type),
                    )
                    return cursor.lastrowid
            except IntegrityError:
                raise
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
        with conn.cursor(True) as cursor:
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
    if not value.isdigit() and not (len(value) == 32 and all(c in "0123456789abcdefABCDEF" for c in value)):
        return None
    if value.isdigit():
        chat = get_chat(int(value))
        if chat:
            return chat
    conn = _get_connection()
    if not conn:
        return None
    with conn:
        with conn.cursor(True) as cursor:
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
    if not value.isdigit() and not (len(value) == 32 and all(c in "0123456789abcdefABCDEF" for c in value)):
        return None
    conn = _get_connection()
    if not conn:
        return None
    with conn:
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
        with conn.cursor(True) as cursor:
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
        fields: List[str] = []
        params: List[Any] = []
        if title is not None:
            fields.append("title=%s")
            params.append(title)
        if pinned is not None:
            fields.append("pinned=%s")
            params.append(bool(pinned))
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
        if user_id is None:
            return None
        if role not in ("user", "assistant"):
            return None
        payload = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO messages (role, content, meta) VALUES (%s, %s, %s) RETURNING id',
                (role, content, payload),
            )
            message_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO chat_details (chat_id, role, message_id, report_id) VALUES (%s, %s, %s, NULL) RETURNING id',
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
        if user_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO chat_details (chat_id, role, message_id, report_id) VALUES (%s, %s, NULL, %s) ON CONFLICT (chat_id,report_id) DO UPDATE SET role=EXCLUDED.role RETURNING id',
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
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO chat_report_refs (chat_id, report_id, source_chat_id, status) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id, report_id) DO UPDATE SET status=EXCLUDED.status, updated_at=CURRENT_TIMESTAMP RETURNING id',
                (chat_id, report_id, source_chat_id, status),
            )
            return cursor.lastrowid


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
        with conn.cursor(True) as cursor:
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
        with conn.cursor(True) as cursor:
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


def _load_files_by_ids(conn, file_ids: List[int]) -> Dict[int, str]:
    if not file_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(file_ids))
    with conn.cursor(True) as cursor:
        cursor.execute(
            f"SELECT id, '/api/assets/' || replace(file_uuid::text, '-', '') AS storage_path FROM files WHERE id IN ({placeholders})",
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
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT ra.report_id AS report_id, '/api/assets/' || replace(f.file_uuid::text, '-', '') AS storage_path "
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
    with conn.cursor(True) as cursor:
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
        video_asset_id = files_map.get(int(row["video_file_id"])) if row.get("video_file_id") is not None else None
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
                "video_asset_id": video_asset_id,
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
    with conn.cursor(True) as cursor:
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
    with conn.cursor(True) as cursor:
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
    if not raw_path: return None
    from app.storage import record
    return record(raw_path,user_id)['id']


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
                "INSERT INTO report_assets (report_id, file_id, asset_kind, sort_order) VALUES (%s, %s, 'representative_image', %s) ON CONFLICT (report_id, file_id, asset_kind) DO UPDATE SET sort_order=EXCLUDED.sort_order RETURNING id",
                (report_id, file_id, idx),
            )


def get_active_report_payloads_for_chat(chat_id: int) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    with conn:
        with conn.cursor(True) as cursor:
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
                    "video_asset_id": report.get("video_asset_id"),
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
        with conn.cursor(True) as cursor:
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
        return _get_report_by_id_with_conn(conn, report_id)


def get_report_by_public_id(report_ref: Any) -> Optional[Dict[str, Any]]:
    value = str(report_ref or "").strip()
    if not value:
        return None
    decoded = decode_public_id(value, expected_kind=KIND_REPORT)
    if decoded:
        value = decoded["uuid_hex"]
    if not value.isdigit() and not (len(value) == 32 and all(c in "0123456789abcdefABCDEF" for c in value)):
        return None
    if value.isdigit():
        report = get_report(int(value))
        if report:
            return report
    conn = _get_connection()
    if not conn:
        return None
    with conn:
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
    if not value.isdigit() and not (len(value) == 32 and all(c in "0123456789abcdefABCDEF" for c in value)):
        return None
    conn = _get_connection()
    if not conn:
        return None
    with conn:
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
                    "video_asset_id": row.get("video_asset_id"),
                    "region_info": row.get("region_info"),
                    "report_json": row.get("report_json"),
                    "representative_images": row.get("representative_images"),
                    "created_at": row.get("created_at"),
                }
            )
        return results


def search_reports_by_chat_title(
    user_id: int,
    keyword: str = "",
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    normalized_keyword = str(keyword or "").strip()
    with conn:
        with conn.cursor(True) as cursor:
            params: List[Any] = [int(user_id)]
            query = (
                "SELECT "
                "c.id AS id, c.chat_uuid AS chat_uuid, c.title AS title, c.chat_type AS chat_type, "
                "c.last_message_at AS last_message_at, c.created_at AS created_at, c.updated_at AS updated_at, "
                "(SELECT rr.id FROM reports rr "
                "WHERE rr.origin_chat_id=c.id AND rr.report_kind='analysis' "
                "AND COALESCE(rr.status, 'active')<>'deleted' "
                "ORDER BY rr.created_at DESC, rr.id DESC LIMIT 1) AS latest_report_id "
                "FROM chats c "
                "WHERE c.user_id=%s "
                "AND c.chat_type<>'bot' "
                "AND EXISTS(SELECT 1 FROM reports re "
                "WHERE re.origin_chat_id=c.id AND re.report_kind='analysis' "
                "AND COALESCE(re.status, 'active')<>'deleted') "
            )
            if normalized_keyword:
                query += "AND c.title ILIKE %s "
                params.append(f"%{normalized_keyword}%")
            query += (
                "ORDER BY COALESCE(c.last_message_at, c.updated_at, c.created_at) DESC "
                "LIMIT %s OFFSET %s"
            )
            params.extend([int(limit), int(offset)])
            cursor.execute(query, tuple(params))
            chat_rows = cursor.fetchall() or []

        report_ids = sorted(
            {
                int(row["latest_report_id"])
                for row in chat_rows
                if row and row.get("latest_report_id") is not None
            }
        )
        reports_map = _get_reports_by_ids_with_conn(conn, report_ids)

        results: List[Dict[str, Any]] = []
        for row in chat_rows:
            latest_report_id = row.get("latest_report_id")
            if latest_report_id is None:
                continue
            report = reports_map.get(int(latest_report_id))
            if not report:
                continue
            report_json = report.get("report_json")
            report_payload = report_json if isinstance(report_json, dict) else {}
            summary = str(report_payload.get("summary") or "").strip()
            if summary and len(summary) > 240:
                summary = f"{summary[:240].rstrip()}..."

            chat_public_id = _to_chat_public_id(row.get("chat_uuid"), fallback=row.get("id"))
            chat_title = str(row.get("title") or "").strip()
            report_title = str(report.get("title") or report_payload.get("title") or "").strip()
            if not chat_title:
                chat_title = report_title or f"Chat {chat_public_id}"

            results.append(
                {
                    "chat_id": chat_public_id,
                    "chat_uuid": chat_public_id,
                    "chat_title": chat_title,
                    "chat_type": row.get("chat_type") or "report",
                    "last_message_at": row.get("last_message_at"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "report": {
                        "report_id": report.get("report_id"),
                        "title": report_title,
                        "source_type": report.get("source_type"),
                        "report_kind": report.get("report_kind"),
                        "summary": summary,
                        "status": report.get("status"),
                        "created_at": report.get("created_at"),
                    },
                }
            )
        return results


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
        safe_title = (title or "Uploaded PDF Report").strip()[:255] or "Uploaded PDF Report"
        preview_text = (extracted_text or "").strip()[:8000]
        for _ in range(5):
            try:
                with conn.cursor() as cursor:
                    report_uuid = uuid7_hex()
                    cursor.execute(
                        "INSERT INTO reports (report_uuid, user_id, report_kind, origin_chat_id, title, status) VALUES (%s, %s, 'pdf', %s, %s, 'active') RETURNING id",
                        (report_uuid, user_id, origin_chat_id, safe_title),
                    )
                    report_id = int(cursor.lastrowid)
                    file_id = _upsert_file_record(conn, user_id, source_path)
                    if file_id is not None:
                        normalized_kind = str(pdf_kind or "uploaded").strip().lower()
                        if normalized_kind not in ("uploaded", "exported"):
                            normalized_kind = "uploaded"
                        cursor.execute(
                            'INSERT INTO report_pdf (report_id, file_id, pdf_kind, derived_from_report_id, content_preview) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (report_id) DO UPDATE SET file_id=EXCLUDED.file_id, pdf_kind=EXCLUDED.pdf_kind, derived_from_report_id=EXCLUDED.derived_from_report_id, content_preview=EXCLUDED.content_preview RETURNING report_id',
                            (report_id, file_id, normalized_kind, derived_from_report_id, preview_text),
                        )
                    return report_id
            except IntegrityError:
                raise
    return None


def delete_pdf_report_and_refs(report_id: int, user_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with conn:
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
        with conn.cursor(True) as cursor:
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
                        "video_asset_id": report.get("video_asset_id") if report else None,
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
        with conn.cursor(True) as cursor:
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
                        "video_asset_id": report.get("video_asset_id") if report else None,
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
    video_asset_id,
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
                        "INSERT INTO reports (report_uuid, user_id, report_kind, origin_chat_id, title, status) VALUES (%s, %s, 'analysis', %s, %s, 'active') RETURNING id",
                        (report_uuid, user_id, chat_id, normalized_title[:255]),
                    )
                    report_id = int(cursor.lastrowid)
                    video_file_id = _upsert_file_record(conn, user_id, video_asset_id)
                    cursor.execute(
                        'INSERT INTO report_analysis (report_id, video_file_id, region_info_json, report_json) VALUES (%s, %s, CAST(%s AS JSONB), CAST(%s AS JSONB)) ON CONFLICT (report_id) DO UPDATE SET video_file_id=EXCLUDED.video_file_id, region_info_json=EXCLUDED.region_info_json, report_json=EXCLUDED.report_json RETURNING report_id',
                        (report_id, video_file_id, payload, report_payload),
                    )
                    _replace_report_assets(conn, report_id, user_id, normalized_images)
                    if chat_id is not None:
                        add_chat_report_detail(chat_id, report_id, user_id)
                    return report_id
            except IntegrityError:
                raise
    return None


def get_latest_report_assets(chat_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return None
    with conn:
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
            "video_asset_id": row.get("video_asset_id"),
            "representative_images": row.get("representative_images"),
            "report_json": row.get("report_json"),
        }
