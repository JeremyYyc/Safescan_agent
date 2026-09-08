"""Phase-one API compatibility over service-owned PostgreSQL schemas."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.persistence.database import get_connection as _get_connection, get_engine
from app.report_errors import require_report_content
from app.utils.public_ids import KIND_CHAT, KIND_REPORT, decode_public_id, encode_public_id
from app.utils.uuid7 import uuid7_hex

REPORT_CHAT = "report"
BOT_CHAT = "bot"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_parse_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _public_id(value: Any, kind: str, fallback: Any = None) -> Optional[str]:
    raw = str(value or "").replace("-", "").lower()
    if len(raw) == 32:
        try:
            return encode_public_id(kind, raw)
        except Exception:
            pass
    return None if fallback is None else str(fallback)


def _decode_id(ref: Any, kind: str) -> Optional[str]:
    raw = str(ref or "").strip()
    decoded = decode_public_id(raw, expected_kind=kind)
    if decoded:
        return decoded["uuid_hex"]
    compact = raw.replace("-", "")
    if len(compact) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in compact):
        return compact.lower()
    return None


def is_db_available() -> bool:
    with get_engine().connect() as conn:
        return conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def _hash_password(password: str) -> str:
    import secrets
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt$16384$8$1${salt}${value}"


_USER_SELECT = """
SELECT u.id AS user_id, replace(u.public_id::text,'-','') AS public_id,
 u.username,u.email,u.avatar,c.secret_hash AS password,
 replace(u.public_id::text,'-','') AS storage_uuid,
 u.account_type,u.status,u.auth_version,
 s.id AS staff_internal_id,replace(s.public_id::text,'-','') AS staff_id,
 r.code AS role,r.version AS role_version,
 cp.customer_status,cp.status_version,
 u.created_at AS create_time,u.updated_at AS update_time
FROM identity_access.users u
LEFT JOIN identity_access.user_credentials c
 ON c.user_id=u.id AND c.credential_type='password' AND c.status='active'
LEFT JOIN identity_access.staff s ON s.user_id=u.id
LEFT JOIN identity_access.roles r ON r.id=s.role_id
LEFT JOIN identity_access.customer_profiles cp ON cp.user_id=u.id
"""


def _get_user(where: str, value: Any) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(_USER_SELECT + f" WHERE {where} LIMIT 1", (value,))
        return cursor.fetchone()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return _get_user("u.email=%s", email.strip().lower())


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    return _get_user("u.username=%s", username)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    return _get_user("u.id=%s", int(user_id))


def get_user_by_subject_id(subject_id: str) -> Optional[Dict[str, Any]]:
    return _get_user("u.public_id=%s", subject_id)


def ensure_user_storage_uuid(user_id: int) -> Optional[str]:
    user = get_user_by_id(user_id)
    return str(user["public_id"]) if user else None


def update_username(user_id: int, username: str) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE identity_access.users SET username=%s,updated_at=NOW() WHERE id=%s", (username, user_id))
        return cursor.rowcount > 0


def create_user(email: str, username: str, password: str, account_type: str = "staff", staff_role: str = "leasing_consultant") -> Optional[Dict[str, Any]]:
    """Create one email account and its exactly-one staff/customer profile."""
    if account_type not in ("staff", "customer"):
        raise ValueError("account_type must be staff or customer")
    public = uuid7_hex()
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO identity_access.users (public_id,email,account_type,username,avatar,status,email_verified_at,auth_version) "
            "VALUES (%s,%s,%s,%s,'','active',NOW(),1) RETURNING id",
            (public, email.strip().lower(), account_type, username),
        )
        user_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO identity_access.user_credentials (user_id,credential_type,secret_hash,algorithm,changed_at,status) "
            "VALUES (%s,'password',%s,'scrypt',NOW(),'active') RETURNING id",
            (user_id, _hash_password(password)),
        )
        if account_type == "staff":
            cursor.execute(
                "INSERT INTO identity_access.staff (public_id,user_id,role_id,staff_code,display_name,employment_status,hired_at) "
                "SELECT %s,%s,r.id,%s,%s,'active',NOW() FROM identity_access.roles r "
                "WHERE r.code=%s AND r.status='active' RETURNING id",
                (uuid7_hex(), user_id, f"EMP-{public[:12].upper()}", username, staff_role),
            )
            if cursor.lastrowid is None:
                raise ValueError(f"Unknown active staff role: {staff_role}")
        else:
            cursor.execute(
                "INSERT INTO identity_access.customer_profiles (user_id,customer_status,status_version,first_prospect_at) "
                "VALUES (%s,'prospect',1,NOW()) RETURNING id", (user_id,),
            )
    return get_user_by_id(user_id)


def verify_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user or user.get("status") != "active" or not user.get("password"):
        return None
    try:
        kind, n, r, p, salt, expected = user["password"].split("$")
        if kind != "scrypt":
            return None
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)).hex()
        return user if hmac.compare_digest(actual, expected) else None
    except (ValueError, KeyError):
        return None


def create_auth_session(user_id: int, expires_at: datetime) -> Optional[str]:
    public = uuid7_hex()
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO identity_access.auth_sessions (public_id,user_id,status,last_seen_at,expires_at) "
            "VALUES (%s,%s,'active',NOW(),%s) RETURNING id", (public, user_id, expires_at),
        )
        return public if cursor.lastrowid else None


def validate_auth_session(session_id: str, user_id: int, auth_version: int) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE identity_access.auth_sessions s SET last_seen_at=NOW(),updated_at=NOW() "
            "FROM identity_access.users u WHERE s.public_id=%s AND s.user_id=%s AND u.id=s.user_id "
            "AND u.auth_version=%s AND u.status='active' AND s.status='active' AND s.expires_at>NOW() RETURNING s.id",
            (session_id, user_id, auth_version),
        )
        return cursor.fetchone() is not None


def revoke_auth_session(session_id: str, reason: str = "logout") -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE identity_access.auth_sessions SET status='revoked',revoked_at=NOW(),revoke_reason=%s,updated_at=NOW() "
            "WHERE public_id=%s AND status='active'", (reason, session_id),
        )
        return cursor.rowcount > 0


def _subject_for_user(conn, user_id: int) -> Optional[str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT public_id FROM identity_access.users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def _staff_for_user(conn, user_id: int) -> Optional[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT s.public_id FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id "
            "WHERE u.id=%s AND u.status='active' AND s.employment_status IN ('active','on_leave')", (user_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def _normalize_chat(row: Optional[Dict[str, Any]], chat_type: str) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    result = dict(row)
    raw_id = int(result["id"])
    internal_id = -raw_id if chat_type == BOT_CHAT else raw_id
    public = _public_id(result.get("public_id"), KIND_CHAT, internal_id)
    result.update(id=public, chat_id=public, chat_uuid=public, internal_id=internal_id, chat_type=chat_type)
    result.setdefault("pinned", False)
    result["last_message_at"] = result.get("last_message_at") or result.get("last_activity_at")
    return result


def create_chat(title: Optional[str] = None, user_id: Optional[int] = None, chat_type: str = REPORT_CHAT) -> Optional[int]:
    if user_id is None or chat_type not in (REPORT_CHAT, BOT_CHAT):
        return None
    with _get_connection() as conn, conn.cursor() as cursor:
        if chat_type == REPORT_CHAT:
            owner = _subject_for_user(conn, user_id)
            if not owner:
                return None
            cursor.execute(
                "INSERT INTO inspection_report.report_workspaces (public_id,created_by_subject_id,title,status,last_activity_at) "
                "VALUES (%s,%s,%s,'active',NOW()) RETURNING id", (uuid7_hex(), owner, title or "New Chat"),
            )
            return int(cursor.lastrowid)
        staff_id = _staff_for_user(conn, user_id)
        if not staff_id:
            return None
        cursor.execute(
            "INSERT INTO staff_agent.staff_sessions (public_id,staff_id,title,status,last_message_at) "
            "VALUES (%s,%s,%s,'active',NOW()) RETURNING id", (uuid7_hex(), staff_id, title or "New Chat"),
        )
        return -int(cursor.lastrowid)


def _get_report_chat(conn, chat_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT w.id,replace(w.public_id::text,'-','') AS public_id,u.id AS user_id,w.title,w.status,w.pinned,"
            "w.last_activity_at,w.created_at,w.updated_at FROM inspection_report.report_workspaces w "
            "JOIN identity_access.users u ON u.public_id=w.created_by_subject_id WHERE w.id=%s AND w.status<>'deleted'", (chat_id,),
        )
        return cursor.fetchone()


def _get_bot_chat(conn, session_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT s.id,replace(s.public_id::text,'-','') AS public_id,u.id AS user_id,s.title,s.status,s.pinned,"
            "s.last_message_at,s.created_at,s.updated_at FROM staff_agent.staff_sessions s "
            "JOIN identity_access.staff st ON st.public_id=s.staff_id JOIN identity_access.users u ON u.id=st.user_id "
            "WHERE s.id=%s AND s.status<>'deleted'", (session_id,),
        )
        return cursor.fetchone()


def get_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        return _normalize_chat(_get_bot_chat(conn, -chat_id), BOT_CHAT) if chat_id < 0 else _normalize_chat(_get_report_chat(conn, chat_id), REPORT_CHAT)


def get_chat_by_public_id(chat_ref: Any) -> Optional[Dict[str, Any]]:
    raw = str(chat_ref or "").strip()
    if raw.lstrip("-").isdigit():
        return get_chat(int(raw))
    public = _decode_id(raw, KIND_CHAT)
    if not public:
        return None
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM inspection_report.report_workspaces WHERE public_id=%s AND status<>'deleted'", (public,))
            row = cursor.fetchone()
        if row:
            return _normalize_chat(_get_report_chat(conn, int(row[0])), REPORT_CHAT)
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM staff_agent.staff_sessions WHERE public_id=%s AND status<>'deleted'", (public,))
            row = cursor.fetchone()
        return _normalize_chat(_get_bot_chat(conn, int(row[0])), BOT_CHAT) if row else None


def resolve_chat_internal_id(chat_ref: Any) -> Optional[int]:
    chat = get_chat_by_public_id(chat_ref)
    return int(chat["internal_id"]) if chat else None


def list_chats(user_id: Optional[int] = None, limit: int = 50, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
    if user_id is None:
        return []
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT * FROM (SELECT w.id,replace(w.public_id::text,'-','') AS public_id,w.title,w.status,w.pinned,"
            "w.last_activity_at AS last_message_at,w.created_at,w.updated_at,'report' AS chat_type,"
            "EXISTS(SELECT 1 FROM inspection_report.reports r JOIN inspection_report.report_analysis a ON a.report_id=r.id "
            "WHERE r.origin_workspace_id=w.id AND r.status='active' AND jsonb_typeof(a.report_payload->'regions')='array' "
            "AND a.report_payload->'regions'<>'[]'::jsonb AND NOT(a.report_payload ? 'error')) AS has_report "
            "FROM inspection_report.report_workspaces w JOIN identity_access.users u ON u.public_id=w.created_by_subject_id "
            "WHERE u.id=%s AND w.status<>'deleted' UNION ALL "
            "SELECT s.id,replace(s.public_id::text,'-','') AS public_id,s.title,s.status,s.pinned,s.last_message_at,"
            "s.created_at,s.updated_at,'bot' AS chat_type,false AS has_report FROM staff_agent.staff_sessions s "
            "JOIN identity_access.staff st ON st.public_id=s.staff_id WHERE st.user_id=%s AND s.status<>'deleted') q "
            "ORDER BY COALESCE(last_message_at,updated_at) DESC LIMIT %s OFFSET %s", (user_id, user_id, limit, offset),
        )
        rows = cursor.fetchall() or []
    return [_normalize_chat(row, row["chat_type"]) for row in rows]


def update_chat_title(chat_id: int, title: str) -> bool:
    table = "staff_agent.staff_sessions" if chat_id < 0 else "inspection_report.report_workspaces"
    ident = -chat_id if chat_id < 0 else chat_id
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET title=%s,updated_at=NOW() WHERE id=%s AND status<>'deleted'", (title, ident))
        return cursor.rowcount > 0


def update_chat_metadata(chat_id: int, title: Optional[str] = None, pinned: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    fields, params = [], []
    if title is not None:
        fields.append("title=%s"); params.append(title)
    if pinned is not None:
        fields.append("pinned=%s"); params.append(bool(pinned))
    if not fields:
        return get_chat(chat_id)
    table = "staff_agent.staff_sessions" if chat_id < 0 else "inspection_report.report_workspaces"
    ident = -chat_id if chat_id < 0 else chat_id
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET {','.join(fields)},updated_at=NOW() WHERE id=%s AND status<>'deleted'", (*params, ident))
    return get_chat(chat_id)


def delete_chat(chat_id: int) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        if chat_id < 0:
            cursor.execute("UPDATE staff_agent.staff_sessions SET status='deleted',updated_at=NOW() WHERE id=%s AND status<>'deleted'", (-chat_id,))
            return cursor.rowcount > 0
        cursor.execute("UPDATE inspection_report.report_workspaces SET status='deleted',updated_at=NOW() WHERE id=%s AND status<>'deleted' RETURNING id", (chat_id,))
        if not cursor.fetchone():
            return False
        cursor.execute("UPDATE inspection_report.reports SET status='deleted',updated_at=NOW() WHERE origin_workspace_id=%s", (chat_id,))
        cursor.execute("DELETE FROM inspection_report.report_assets WHERE report_id IN (SELECT id FROM inspection_report.reports WHERE origin_workspace_id=%s)", (chat_id,))
        cursor.execute("DELETE FROM inspection_report.report_pdf WHERE report_id IN (SELECT id FROM inspection_report.reports WHERE origin_workspace_id=%s)", (chat_id,))
        cursor.execute("DELETE FROM inspection_report.report_analysis WHERE report_id IN (SELECT id FROM inspection_report.reports WHERE origin_workspace_id=%s)", (chat_id,))
        return True


def _next_workspace_sequence(conn, workspace_id: int) -> int:
    with conn.cursor() as cursor:
        cursor.execute("UPDATE inspection_report.report_workspaces SET next_sequence=next_sequence+1,last_activity_at=NOW(),updated_at=NOW() WHERE id=%s AND status='active' RETURNING next_sequence-1", (workspace_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Report workspace not found")
        return int(row[0])


def _next_staff_sequence(conn, session_id: int) -> int:
    with conn.cursor() as cursor:
        cursor.execute("UPDATE staff_agent.staff_sessions SET next_sequence=next_sequence+1,last_message_at=NOW(),updated_at=NOW() WHERE id=%s AND status='active' RETURNING next_sequence-1", (session_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Staff session not found")
        return int(row[0])


def add_chat_message(chat_id: int, role: str, content: str, user_id: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
    if user_id is None or role not in ("user", "assistant"):
        return None
    with _get_connection() as conn, conn.cursor() as cursor:
        if chat_id < 0:
            session_id = -chat_id
            sequence = _next_staff_sequence(conn, session_id)
            cursor.execute("INSERT INTO staff_agent.staff_messages (public_id,session_id,sequence_no,role,kind,content,status,metadata_redacted) VALUES (%s,%s,%s,%s,'text',%s,'completed',CAST(%s AS jsonb)) RETURNING id", (uuid7_hex(), session_id, sequence, role, content, _json(meta or {})))
            return int(cursor.lastrowid)
        sequence = _next_workspace_sequence(conn, chat_id)
        cursor.execute("INSERT INTO inspection_report.report_workspace_messages (workspace_id,role,kind,content,metadata_redacted) VALUES (%s,%s,'text',%s,CAST(%s AS jsonb)) RETURNING id", (chat_id, role, content, _json(meta or {})))
        message_id = int(cursor.lastrowid)
        cursor.execute("INSERT INTO inspection_report.report_workspace_items (workspace_id,sequence_no,item_type,message_id) VALUES (%s,%s,'message',%s) RETURNING id", (chat_id, sequence, message_id))
        return message_id


def add_chat_report_detail(chat_id: int, report_id: int, user_id: Optional[int] = None) -> Optional[int]:
    if user_id is None or chat_id < 0:
        return None
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id FROM inspection_report.report_workspace_items WHERE workspace_id=%s AND report_id=%s", (chat_id, report_id))
        row = cursor.fetchone()
        if row:
            return int(row[0])
        sequence = _next_workspace_sequence(conn, chat_id)
        cursor.execute("INSERT INTO inspection_report.report_workspace_items (workspace_id,sequence_no,item_type,report_id) VALUES (%s,%s,'report',%s) RETURNING id", (chat_id, sequence, report_id))
        return int(cursor.lastrowid)


def add_chat_report_ref(chat_id: int, report_id: int, source_chat_id: Optional[int] = None, status: str = "active") -> Optional[int]:
    if chat_id >= 0:
        report = get_report(report_id)
        return add_chat_report_detail(chat_id, report_id, report.get("user_id") if report else None)
    normalized = "removed" if status in ("removed", "deleted") else "active"
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT public_id FROM inspection_report.reports WHERE id=%s", (report_id,))
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute(
            "INSERT INTO staff_agent.staff_session_resources (session_id,resource_type,resource_id,purpose,status,metadata_redacted) "
            "VALUES (%s,'report',%s,'chat_context',%s,CAST(%s AS jsonb)) ON CONFLICT (session_id,resource_type,resource_id,purpose) "
            "DO UPDATE SET status=EXCLUDED.status,metadata_redacted=EXCLUDED.metadata_redacted,updated_at=NOW() RETURNING id",
            (-chat_id, row[0], normalized, _json({"source_workspace_id": source_chat_id})),
        )
        return int(cursor.lastrowid)


def set_chat_report_ref_status(chat_id: int, report_id: int, status: str) -> bool:
    if chat_id >= 0:
        return False
    normalized = "removed" if status in ("removed", "deleted") else status
    if normalized not in ("active", "removed"):
        return False
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE staff_agent.staff_session_resources sr SET status=%s,updated_at=NOW() FROM inspection_report.reports r WHERE sr.session_id=%s AND sr.resource_type='report' AND sr.resource_id=r.public_id AND r.id=%s", (normalized, -chat_id, report_id))
        return cursor.rowcount > 0


def list_chat_report_refs(chat_id: int) -> List[Dict[str, Any]]:
    if chat_id >= 0:
        return []
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT sr.id,%s AS chat_id,r.id AS report_id,r.origin_workspace_id AS source_chat_id,"
            "CASE WHEN r.status='deleted' THEN 'deleted' ELSE sr.status END AS status,sr.created_at,sr.updated_at "
            "FROM staff_agent.staff_session_resources sr LEFT JOIN inspection_report.reports r ON r.public_id=sr.resource_id "
            "WHERE sr.session_id=%s AND sr.resource_type='report' ORDER BY sr.created_at", (chat_id, -chat_id),
        )
        return cursor.fetchall() or []


def list_chat_report_refs_enriched(chat_id: int) -> List[Dict[str, Any]]:
    output = []
    for ref in list_chat_report_refs(chat_id):
        report = get_report(int(ref["report_id"])) if ref.get("report_id") is not None else None
        source_id = ref.get("source_chat_id") or (report or {}).get("origin_chat_id")
        source = get_chat(int(source_id)) if source_id else None
        output.append({**ref, "source_chat_internal_id": source_id, "source_chat_id": source.get("id") if source else None, "source_chat_title": source.get("title") if source else None, "report": report if report and report.get("status") != "deleted" else None})
    return output


def _load_files_by_ids(conn, file_ids: List[int]) -> Dict[int, str]:
    if not file_ids:
        return {}
    marks = ",".join(["%s"] * len(file_ids))
    with conn.cursor(True) as cursor:
        cursor.execute(f"SELECT id,'/api/assets/'||replace(public_id::text,'-','') AS storage_path FROM inspection_report.files WHERE id IN ({marks})", tuple(file_ids))
        return {int(row["id"]): row["storage_path"] for row in cursor.fetchall() or []}


def _load_report_asset_images(conn, report_ids: List[int]) -> Dict[int, List[str]]:
    if not report_ids:
        return {}
    marks = ",".join(["%s"] * len(report_ids))
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT ra.report_id,'/api/assets/'||replace(f.public_id::text,'-','') AS storage_path "
            "FROM inspection_report.report_assets ra JOIN inspection_report.files f ON f.id=ra.file_id "
            f"WHERE ra.asset_kind='evidence_image' AND ra.report_id IN ({marks}) ORDER BY ra.report_id,ra.sort_order,ra.id",
            tuple(report_ids),
        )
        rows = cursor.fetchall() or []
    output: Dict[int, List[str]] = {}
    for row in rows:
        output.setdefault(int(row["report_id"]), []).append(row["storage_path"])
    return output


def _normalize_report(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    result = dict(row)
    internal = int(result["id"])
    public = _public_id(result.get("public_id"), KIND_REPORT, internal)
    result.update(report_id=public, report_uuid=public)
    result["source_type"] = "pdf" if result.get("report_kind") == "pdf" else "video"
    result["chat_id"] = result.get("origin_workspace_id")
    result["origin_chat_id"] = result.get("origin_workspace_id")
    result["region_info"] = _safe_parse_json(result.get("region_info"))
    result["report_json"] = _safe_parse_json(result.get("report_json"))
    result["representative_images"] = _safe_parse_json(result.get("representative_images")) or []
    return result


def _fetch_reports_enriched(conn, where: str, params: Tuple[Any, ...], order: str = "", limit: str = "") -> List[Dict[str, Any]]:
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT r.id,replace(r.public_id::text,'-','') AS public_id,u.id AS user_id,r.report_kind,"
            "r.origin_workspace_id,r.title,r.status,r.source,r.created_at,r.updated_at,"
            "a.video_file_id,a.region_info,a.report_payload AS report_json,a.validation_passed,a.validation_errors,"
            "p.file_id AS pdf_file_id,p.pdf_kind,p.derived_from_report_id,p.content_preview "
            "FROM inspection_report.reports r JOIN identity_access.users u ON u.public_id=r.created_by_subject_id "
            "LEFT JOIN inspection_report.report_analysis a ON a.report_id=r.id "
            "LEFT JOIN inspection_report.report_pdf p ON p.report_id=r.id "
            f"{where} {order} {limit}", params,
        )
        rows = cursor.fetchall() or []
    file_ids = {int(row[key]) for row in rows for key in ("video_file_id", "pdf_file_id") if row.get(key) is not None}
    files = _load_files_by_ids(conn, list(file_ids))
    images = _load_report_asset_images(conn, [int(row["id"]) for row in rows])
    output = []
    for row in rows:
        item = dict(row)
        item["video_asset_id"] = files.get(int(row["video_file_id"])) if row.get("video_file_id") else None
        item["source_path"] = files.get(int(row["pdf_file_id"])) if row.get("pdf_file_id") else item["video_asset_id"]
        item["representative_images"] = images.get(int(row["id"]), [])
        output.append(_normalize_report(item))
    return output


def _get_reports_by_ids_with_conn(conn, report_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not report_ids:
        return {}
    marks = ",".join(["%s"] * len(report_ids))
    return {int(row["id"]): row for row in _fetch_reports_enriched(conn, f"WHERE r.id IN ({marks})", tuple(report_ids))}


def _file_id(conn, ref: Any, user_id: Optional[int] = None) -> Optional[int]:
    public = str(ref or "").removeprefix("/api/assets/").replace("-", "")
    if len(public) != 32 or not all(ch in "0123456789abcdefABCDEF" for ch in public):
        return None
    with conn.cursor() as cursor:
        if user_id is None:
            cursor.execute("SELECT id FROM inspection_report.files WHERE public_id=%s AND status='ready'", (public,))
        else:
            cursor.execute("SELECT f.id FROM inspection_report.files f JOIN identity_access.users u ON u.public_id=f.created_by_subject_id WHERE f.public_id=%s AND u.id=%s AND f.status='ready'", (public, user_id))
        row = cursor.fetchone()
        return int(row[0]) if row else None


def _upsert_file_record(conn, user_id: Optional[int], raw_path: Any) -> Optional[int]:
    return _file_id(conn, raw_path, user_id)


def _replace_report_assets(conn, report_id: int, user_id: Optional[int], refs: List[str]) -> None:
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM inspection_report.report_assets WHERE report_id=%s AND asset_kind='evidence_image'", (report_id,))
        for order, ref in enumerate(refs):
            file_id = _file_id(conn, ref, user_id)
            if file_id is None:
                raise ValueError("Evidence asset not found")
            cursor.execute("INSERT INTO inspection_report.report_assets (report_id,file_id,asset_kind,sort_order) VALUES (%s,%s,'evidence_image',%s) RETURNING id", (report_id, file_id, order))


def get_report(report_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = _fetch_reports_enriched(conn, "WHERE r.id=%s", (report_id,), limit="LIMIT 1")
        return rows[0] if rows else None


def get_report_by_public_id(report_ref: Any) -> Optional[Dict[str, Any]]:
    raw = str(report_ref or "").strip()
    if raw.isdigit():
        return get_report(int(raw))
    public = _decode_id(raw, KIND_REPORT)
    if not public:
        return None
    with _get_connection() as conn:
        rows = _fetch_reports_enriched(conn, "WHERE r.public_id=%s", (public,), limit="LIMIT 1")
        return rows[0] if rows else None


def resolve_report_internal_id(report_ref: Any) -> Optional[int]:
    report = get_report_by_public_id(report_ref)
    return int(report["id"]) if report else None


def list_reports_by_chat(chat_id: int) -> List[Dict[str, Any]]:
    if chat_id < 0:
        return []
    with _get_connection() as conn:
        return _fetch_reports_enriched(conn, "WHERE r.origin_workspace_id=%s", (chat_id,), order="ORDER BY r.created_at")


def search_reports_by_chat_title(user_id: int, keyword: str = "", limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    normalized = str(keyword or "").strip()
    with _get_connection() as conn, conn.cursor(True) as cursor:
        params: List[Any] = [user_id]
        query = (
            "SELECT w.id,replace(w.public_id::text,'-','') AS public_id,w.title,w.last_activity_at AS last_message_at,w.created_at,w.updated_at,"
            "(SELECT r.id FROM inspection_report.reports r WHERE r.origin_workspace_id=w.id AND r.report_kind='analysis' AND r.status='active' ORDER BY r.created_at DESC,r.id DESC LIMIT 1) latest_report_id "
            "FROM inspection_report.report_workspaces w JOIN identity_access.users u ON u.public_id=w.created_by_subject_id "
            "WHERE u.id=%s AND w.status<>'deleted' AND EXISTS(SELECT 1 FROM inspection_report.reports e WHERE e.origin_workspace_id=w.id AND e.report_kind='analysis' AND e.status='active') "
        )
        if normalized:
            query += "AND w.title ILIKE %s "; params.append(f"%{normalized}%")
        query += "ORDER BY w.last_activity_at DESC LIMIT %s OFFSET %s"; params.extend([limit, offset])
        cursor.execute(query, tuple(params)); chats = cursor.fetchall() or []
        reports = _get_reports_by_ids_with_conn(conn, [int(row["latest_report_id"]) for row in chats])
    output = []
    for row in chats:
        report = reports.get(int(row["latest_report_id"]))
        if not report:
            continue
        payload = report.get("report_json") if isinstance(report.get("report_json"), dict) else {}
        public = _public_id(row["public_id"], KIND_CHAT, row["id"])
        output.append({"chat_id": public, "chat_uuid": public, "chat_title": row.get("title") or report.get("title"), "chat_type": REPORT_CHAT,
            "last_message_at": row.get("last_message_at"), "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
            "report": {"report_id": report.get("report_id"), "title": report.get("title"), "source_type": report.get("source_type"), "report_kind": report.get("report_kind"), "summary": str(payload.get("summary") or "")[:240], "status": report.get("status"), "created_at": report.get("created_at")}})
    return output


def store_pdf_report(*, user_id: int, source_path: str, title: str, extracted_text: str = "", origin_chat_id: Optional[int] = None, pdf_kind: str = "uploaded", derived_from_report_id: Optional[int] = None) -> Optional[int]:
    normalized_kind = pdf_kind if pdf_kind in ("uploaded", "exported") else "uploaded"
    with _get_connection() as conn, conn.cursor() as cursor:
        owner = _subject_for_user(conn, user_id); file_id = _file_id(conn, source_path, user_id)
        if not owner or file_id is None:
            return None
        source = "exported_pdf" if normalized_kind == "exported" else "uploaded_pdf"
        cursor.execute("UPDATE inspection_report.files SET purpose=%s,updated_at=NOW() WHERE id=%s", (source, file_id))
        cursor.execute("INSERT INTO inspection_report.reports (public_id,created_by_subject_id,origin_workspace_id,report_kind,source,title,status,schema_version,pipeline_version,completed_at) VALUES (%s,%s,%s,'pdf',%s,%s,'active',1,'pdf-v1',NOW()) RETURNING id", (uuid7_hex(), owner, origin_chat_id if origin_chat_id and origin_chat_id > 0 else None, source, (title or "Uploaded PDF Report")[:255]))
        report_id = int(cursor.lastrowid)
        cursor.execute("INSERT INTO inspection_report.report_pdf (report_id,file_id,pdf_kind,derived_from_report_id,content_preview) VALUES (%s,%s,%s,%s,%s) RETURNING report_id", (report_id, file_id, normalized_kind, derived_from_report_id, (extracted_text or "")[:8000]))
        if normalized_kind == "exported":
            cursor.execute("INSERT INTO inspection_report.report_assets (report_id,file_id,asset_kind,sort_order) VALUES (%s,%s,'exported_pdf',0) RETURNING id", (report_id, file_id))
        if origin_chat_id and origin_chat_id > 0:
            add_chat_report_detail(origin_chat_id, report_id, user_id)
        return report_id


def delete_pdf_report_and_refs(report_id: int, user_id: int) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE inspection_report.reports r SET status='deleted',updated_at=NOW() FROM identity_access.users u WHERE r.id=%s AND r.report_kind='pdf' AND r.created_by_subject_id=u.public_id AND u.id=%s AND r.status<>'deleted' RETURNING r.id", (report_id, user_id))
        if not cursor.fetchone():
            return False
        cursor.execute("DELETE FROM inspection_report.report_assets WHERE report_id=%s", (report_id,))
        cursor.execute("DELETE FROM inspection_report.report_pdf WHERE report_id=%s", (report_id,))
        return True


def get_latest_report_id(chat_id: int) -> Optional[int]:
    if chat_id < 0:
        return None
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id FROM inspection_report.reports WHERE origin_workspace_id=%s AND report_kind='analysis' AND status='active' ORDER BY created_at DESC,id DESC LIMIT 1", (chat_id,))
        row = cursor.fetchone(); return int(row[0]) if row else None


def get_latest_pdf_for_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    if chat_id < 0:
        return None
    with _get_connection() as conn:
        rows = _fetch_reports_enriched(conn, "WHERE r.origin_workspace_id=%s AND r.report_kind='pdf' AND r.status='active'", (chat_id,), order="ORDER BY r.created_at DESC,r.id DESC", limit="LIMIT 1")
        return rows[0] if rows else None


def get_active_report_payloads_for_chat(chat_id: int) -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        if chat_id < 0:
            with conn.cursor() as cursor:
                cursor.execute("SELECT r.id FROM staff_agent.staff_session_resources sr JOIN inspection_report.reports r ON r.public_id=sr.resource_id WHERE sr.session_id=%s AND sr.resource_type='report' AND sr.status='active' AND r.status='active' ORDER BY sr.created_at", (-chat_id,))
                ids = [int(row[0]) for row in cursor.fetchall() or []]
            reports = _get_reports_by_ids_with_conn(conn, ids)
            return [reports[i] for i in ids if i in reports and isinstance(reports[i].get("report_json"), dict)]
        rows = _fetch_reports_enriched(conn, "WHERE r.origin_workspace_id=%s AND r.status='active'", (chat_id,), order="ORDER BY r.created_at")
        return [row for row in rows if isinstance(row.get("report_json"), dict)]


def _workspace_messages(conn, chat_id: int, limit: int, offset: int, descending: bool = False) -> List[Dict[str, Any]]:
    direction = "DESC" if descending else "ASC"
    with conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT i.id,i.workspace_id AS chat_id,i.item_type,m.role,m.content,m.metadata_redacted AS meta,i.report_id,i.created_at "
            "FROM inspection_report.report_workspace_items i LEFT JOIN inspection_report.report_workspace_messages m ON m.id=i.message_id "
            f"WHERE i.workspace_id=%s AND i.item_type IN ('message','report') ORDER BY i.sequence_no {direction} LIMIT %s OFFSET %s", (chat_id, limit, offset),
        )
        rows = cursor.fetchall() or []
    reports = _get_reports_by_ids_with_conn(conn, [int(row["report_id"]) for row in rows if row.get("report_id")])
    output = []
    for row in rows:
        if row["item_type"] == "report":
            report = reports.get(int(row["report_id"]))
            output.append({"id": row["id"], "chat_id": chat_id, "role": "report", "content": report.get("region_info") if report else None,
                "meta": {"type": "region_info", "video_asset_id": report.get("video_asset_id") if report else None, "representative_images": report.get("representative_images") if report else None, "report": report.get("report_json") if report else None}, "created_at": row["created_at"]})
        else:
            output.append({"id": row["id"], "chat_id": chat_id, "role": row["role"], "content": row["content"], "meta": row.get("meta") or {}, "created_at": row["created_at"]})
    return output


def get_chat_messages(chat_id: int, limit: int = 50, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
    with _get_connection() as conn:
        if chat_id >= 0:
            return _workspace_messages(conn, chat_id, limit, offset)
        with conn.cursor(True) as cursor:
            cursor.execute("SELECT id,%s AS chat_id,role,content,metadata_redacted AS meta,created_at FROM staff_agent.staff_messages WHERE session_id=%s ORDER BY sequence_no LIMIT %s OFFSET %s", (chat_id, -chat_id, limit, offset))
            return cursor.fetchall() or []


def get_recent_chat_messages(chat_id: int, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
    with _get_connection() as conn:
        if chat_id >= 0:
            return _workspace_messages(conn, chat_id, limit, 0, True)
        with conn.cursor(True) as cursor:
            cursor.execute("SELECT id,%s AS chat_id,role,content,metadata_redacted AS meta,created_at FROM staff_agent.staff_messages WHERE session_id=%s ORDER BY sequence_no DESC LIMIT %s", (chat_id, -chat_id, limit))
            return cursor.fetchall() or []


def get_recent_user_questions(chat_id: int, limit: int = 20) -> List[str]:
    with _get_connection() as conn, conn.cursor() as cursor:
        if chat_id < 0:
            cursor.execute("SELECT content FROM staff_agent.staff_messages WHERE session_id=%s AND role='user' ORDER BY sequence_no DESC LIMIT %s", (-chat_id, limit))
        else:
            cursor.execute("SELECT m.content FROM inspection_report.report_workspace_items i JOIN inspection_report.report_workspace_messages m ON m.id=i.message_id WHERE i.workspace_id=%s AND m.role='user' ORDER BY i.sequence_no DESC LIMIT %s", (chat_id, limit))
        return [row[0] for row in reversed(cursor.fetchall() or [])]


def get_latest_report_region_info(chat_id: int) -> Optional[List[Any]]:
    report_id = get_latest_report_id(chat_id)
    report = get_report(report_id) if report_id else None
    return report.get("region_info") if report and isinstance(report.get("region_info"), list) else None


def chat_has_report(chat_id: int) -> bool:
    return get_latest_report_id(chat_id) is not None


def store_report(region_info, video_asset_id, report_data: Optional[Dict[str, Any]] = None, representative_images: Optional[List[str]] = None, chat_id: Optional[int] = None, user_id: Optional[int] = None):
    require_report_content(report_data)
    if region_info is None or user_id is None or chat_id is None or chat_id < 0:
        return None
    with _get_connection() as conn, conn.cursor() as cursor:
        owner = _subject_for_user(conn, user_id); video_file_id = _file_id(conn, video_asset_id, user_id)
        if not owner or video_file_id is None:
            return None
        title = str((report_data or {}).get("title") or f"Report {chat_id}")[:255]
        cursor.execute("INSERT INTO inspection_report.reports (public_id,created_by_subject_id,origin_workspace_id,report_kind,source,title,status,schema_version,pipeline_version,completed_at) VALUES (%s,%s,%s,'analysis','video_analysis',%s,'active',1,'langgraph-v1',NOW()) RETURNING id", (uuid7_hex(), owner, chat_id, title))
        report_id = int(cursor.lastrowid)
        cursor.execute("INSERT INTO inspection_report.report_analysis (report_id,video_file_id,region_info,report_payload,validation_passed,validation_errors) VALUES (%s,%s,CAST(%s AS jsonb),CAST(%s AS jsonb),true,'[]'::jsonb) RETURNING report_id", (report_id, video_file_id, _json(region_info), _json(report_data)))
        cursor.execute("INSERT INTO inspection_report.report_assets (report_id,file_id,asset_kind,sort_order) VALUES (%s,%s,'input_video',0) RETURNING id", (report_id, video_file_id))
        _replace_report_assets(conn, report_id, user_id, representative_images or [])
        add_chat_report_detail(chat_id, report_id, user_id)
        return report_id


def get_latest_report_assets(chat_id: int) -> Optional[Dict[str, Any]]:
    report_id = get_latest_report_id(chat_id); report = get_report(report_id) if report_id else None
    if not report:
        return None
    return {"video_asset_id": report.get("video_asset_id"), "video_path": report.get("video_asset_id"), "representative_images": report.get("representative_images"), "report_json": report.get("report_json")}


# Durable report workflow jobs
def create_report_job(*, user_id: int, workspace_id: int, video_asset_id: str, attributes: Dict[str, Any], pipeline_version: str, max_attempts: int = 3) -> Dict[str, Any]:
    public, idempotency = uuid7_hex(), uuid4().hex
    with _get_connection() as conn, conn.cursor() as cursor:
        owner = _subject_for_user(conn, user_id); file_id = _file_id(conn, video_asset_id, user_id)
        if not owner or file_id is None:
            raise ValueError("Video asset not found")
        cursor.execute("SELECT 1 FROM inspection_report.report_workspaces WHERE id=%s AND created_by_subject_id=%s AND status='active'", (workspace_id, owner))
        if not cursor.fetchone():
            raise PermissionError("Report workspace not found")
        cursor.execute("INSERT INTO inspection_report.report_jobs (public_id,requested_by_subject_id,workspace_id,job_type,input_file_id,queue,priority,status,attempt,max_attempts,available_at,idempotency_key,pipeline_version,input_payload) VALUES (%s,%s,%s,'video_analysis',%s,'report-analysis',0,'queued',0,%s,NOW(),%s,%s,CAST(%s AS jsonb)) RETURNING id", (public, owner, workspace_id, file_id, max_attempts, idempotency, pipeline_version, _json({"attributes": attributes or {}})))
        job_id = int(cursor.lastrowid); sequence = _next_workspace_sequence(conn, workspace_id)
        cursor.execute("INSERT INTO inspection_report.report_workspace_items (workspace_id,sequence_no,item_type,job_id) VALUES (%s,%s,'job',%s) RETURNING id", (workspace_id, sequence, job_id))
        append_report_job_event(job_id, "queued", "queued", 0, "报告任务已进入队列", {})
    return get_report_job(job_id)


def _normalize_job(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    result = dict(row); result["job_id"] = str(result.get("public_id") or "").replace("-", "")
    result["input_payload"] = _safe_parse_json(result.get("input_payload")) or {}; result["result_payload"] = _safe_parse_json(result.get("result_payload"))
    if result.get("input_file_public_id"):
        result["video_asset_id"] = "/api/assets/" + str(result["input_file_public_id"]).replace("-", "")
    return result


def get_report_job(job_ref: Any) -> Optional[Dict[str, Any]]:
    raw = str(job_ref or "").strip().replace("-", "")
    if raw.isdigit(): condition, value = "j.id=%s", int(raw)
    elif len(raw) == 32: condition, value = "j.public_id=%s", raw
    else: return None
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute("SELECT j.*,replace(j.public_id::text,'-','') AS public_id,replace(f.public_id::text,'-','') AS input_file_public_id,u.id AS user_id FROM inspection_report.report_jobs j JOIN identity_access.users u ON u.public_id=j.requested_by_subject_id LEFT JOIN inspection_report.files f ON f.id=j.input_file_id WHERE " + condition, (value,))
        return _normalize_job(cursor.fetchone())


def append_report_job_event(job_id: int, event_type: str, stage: str, progress_percent: Optional[float], message: Optional[str], payload: Optional[Dict[str, Any]] = None) -> int:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id FROM inspection_report.report_jobs WHERE id=%s FOR UPDATE", (job_id,))
        if not cursor.fetchone(): raise ValueError("Report job not found")
        cursor.execute("SELECT COALESCE(MAX(sequence_no),0)+1 FROM inspection_report.report_job_events WHERE job_id=%s", (job_id,)); sequence = int(cursor.fetchone()[0])
        cursor.execute("INSERT INTO inspection_report.report_job_events (job_id,sequence_no,event_type,stage,progress_percent,message,payload_redacted) VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS jsonb)) RETURNING id", (job_id, sequence, event_type, stage, progress_percent, message, _json(payload or {})))
        if progress_percent is not None:
            cursor.execute("UPDATE inspection_report.report_jobs SET progress_percent=%s,heartbeat_at=CASE WHEN status='running' THEN NOW() ELSE heartbeat_at END,updated_at=NOW() WHERE id=%s", (progress_percent, job_id))
        return sequence


def get_report_job_events(job_id: int, after_sequence: int = 0) -> List[Dict[str, Any]]:
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute("SELECT sequence_no,event_type,stage,progress_percent,message,payload_redacted AS payload,created_at FROM inspection_report.report_job_events WHERE job_id=%s AND sequence_no>%s ORDER BY sequence_no", (job_id, after_sequence))
        return cursor.fetchall() or []


def record_report_job_step(job_id: int, attempt: int, step_event: str, metrics: Optional[Dict[str, Any]] = None) -> None:
    suffix = "_start" if step_event.endswith("_start") else "_complete" if step_event.endswith("_complete") else ""
    if not suffix:
        return
    step_name = step_event[:-len(suffix)]
    status = "running" if suffix == "_start" else "completed"
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO inspection_report.report_job_steps (job_id,step_name,attempt,status,started_at,finished_at,metrics) "
            "VALUES (%s,%s,%s,%s,NOW(),CASE WHEN %s='completed' THEN NOW() ELSE NULL END,CAST(%s AS jsonb)) "
            "ON CONFLICT (job_id,step_name,attempt) DO UPDATE SET status=EXCLUDED.status,"
            "finished_at=CASE WHEN EXCLUDED.status='completed' THEN NOW() ELSE inspection_report.report_job_steps.finished_at END,"
            "metrics=EXCLUDED.metrics,updated_at=NOW()",
            (job_id, step_name, attempt, status, status, _json(metrics or {})),
        )


def get_report_job_steps(job_id: int) -> List[Dict[str, Any]]:
    with _get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute("SELECT step_name,attempt,status,started_at,finished_at,metrics,error_code FROM inspection_report.report_job_steps WHERE job_id=%s ORDER BY attempt,id", (job_id,))
        return cursor.fetchall() or []


def recover_stale_report_jobs() -> int:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE inspection_report.report_jobs SET status=CASE WHEN attempt<max_attempts THEN 'retry_wait' ELSE 'failed' END,available_at=NOW(),worker_id=NULL,lease_until=NULL,error_code='worker_lease_expired',finished_at=CASE WHEN attempt>=max_attempts THEN NOW() ELSE NULL END,updated_at=NOW() WHERE status='running' AND lease_until<NOW()")
        return cursor.rowcount


def claim_report_job(worker_id: str, lease_seconds: int, job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    extra = "AND id=%s" if job_id is not None else ""
    params: Tuple[Any, ...] = (job_id, worker_id, lease_seconds) if job_id is not None else (worker_id, lease_seconds)
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("WITH candidate AS (SELECT id FROM inspection_report.report_jobs WHERE status IN ('queued','retry_wait') AND available_at<=NOW() " + extra + " ORDER BY priority DESC,available_at,id FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE inspection_report.report_jobs j SET status='running',attempt=j.attempt+1,worker_id=%s,lease_until=NOW()+(%s||' seconds')::interval,heartbeat_at=NOW(),updated_at=NOW() FROM candidate WHERE j.id=candidate.id RETURNING j.id", params)
        row = cursor.fetchone(); claimed = int(row[0]) if row else None
    if not claimed: return None
    append_report_job_event(claimed, "running", "workflow", 1, "开始执行报告工作流", {"worker_id": worker_id})
    return get_report_job(claimed)


def heartbeat_report_job(job_id: int, worker_id: str, lease_seconds: int, progress: Optional[float] = None) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE inspection_report.report_jobs SET heartbeat_at=NOW(),lease_until=NOW()+(%s||' seconds')::interval,progress_percent=COALESCE(%s,progress_percent),updated_at=NOW() WHERE id=%s AND worker_id=%s AND status='running'", (lease_seconds, progress, job_id, worker_id))
        return cursor.rowcount > 0


def link_report_job_report(job_id: int, report_id: int) -> bool:
    with _get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE inspection_report.report_jobs SET report_id=%s,updated_at=NOW() WHERE id=%s AND (report_id IS NULL OR report_id=%s)", (report_id, job_id, report_id))
        return cursor.rowcount > 0


def complete_report_job(job_id: int, result: Dict[str, Any]) -> bool:
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE inspection_report.report_jobs SET status='completed',progress_percent=100,result_payload=CAST(%s AS jsonb),finished_at=NOW(),lease_until=NULL,worker_id=NULL,updated_at=NOW() WHERE id=%s AND status='running'", (_json(result), job_id))
            changed = cursor.rowcount > 0
        if changed:
            append_report_job_event(job_id, "complete", "complete", 100, "报告生成完成", {"result": result})
        return changed


def fail_report_job(job_id: int, error_code: str, message: str, retry: bool = False) -> str:
    with _get_connection() as conn:
        with conn.cursor(True) as cursor:
            cursor.execute("SELECT attempt,max_attempts FROM inspection_report.report_jobs WHERE id=%s FOR UPDATE", (job_id,)); row = cursor.fetchone()
            if not row: return "missing"
            should_retry = retry and int(row["attempt"]) < int(row["max_attempts"]); status = "retry_wait" if should_retry else "failed"
            cursor.execute("UPDATE inspection_report.report_jobs SET status=%s,error_code=%s,available_at=CASE WHEN %s THEN NOW()+INTERVAL '1 second' ELSE available_at END,finished_at=CASE WHEN %s THEN NULL ELSE NOW() END,lease_until=NULL,worker_id=NULL,updated_at=NOW() WHERE id=%s", (status, error_code, should_retry, should_retry, job_id))
        append_report_job_event(job_id, "retry" if should_retry else "error", "failed", None, message, {"code": error_code})
        return status
