import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pymysql

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.report import BASE_DIR, OUTPUT_DIR
from app.db import _get_connection, _ensure_core_tables, ensure_user_storage_uuid


def _normalize_path(raw: str) -> str:
    return str(raw or "").replace("\\", "/")


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _safe_move(src: Path, dst: Path, dry_run: bool = False) -> Tuple[bool, str]:
    if src.resolve() == dst.resolve():
        return True, "same_path"
    if not src.exists() and dst.exists():
        return True, "already_moved"
    if not src.exists():
        return False, "src_missing"
    if dst.exists():
        return False, "dst_exists"
    if dry_run:
        return True, "dry_run"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True, "moved"


def _load_user_storage_map(conn) -> Dict[int, str]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall() or []
    result: Dict[int, str] = {}
    for row in users:
        user_id = int(row["user_id"])
        storage_uuid = ensure_user_storage_uuid(user_id)
        if storage_uuid:
            result[user_id] = storage_uuid
    return result


def _collect_video_reports(conn) -> List[Dict]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, user_id, video_path, representative_images, region_info, report_json "
            "FROM reports WHERE video_path IS NOT NULL AND video_path<>''"
        )
        return cursor.fetchall() or []


def _collect_pdf_reports(conn) -> List[Dict]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT id, user_id, source_path FROM reports "
            "WHERE source_path IS NOT NULL AND source_path<>'' "
            "AND (source_type='pdf' OR LOWER(source_path) LIKE '%.pdf')"
        )
        return cursor.fetchall() or []


def _build_new_video_path(src: Path, storage_uuid: str) -> Path:
    suffix = src.suffix or ".mp4"
    stem = src.stem
    return OUTPUT_DIR / storage_uuid / "Videos" / "originals" / f"{stem}{suffix}"


def _build_new_pdf_path(src: Path, storage_uuid: str) -> Path:
    suffix = src.suffix or ".pdf"
    stem = src.stem
    return OUTPUT_DIR / storage_uuid / "PDF" / f"{stem}{suffix}"


def _parse_images(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    try:
        import json

        value = json.loads(raw_value)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _dump_images(images: List[str]) -> str:
    import json

    return json.dumps(images, ensure_ascii=False)


def _replace_prefix(images: List[str], old_prefix: str, new_prefix: str) -> List[str]:
    old_norm = _normalize_path(old_prefix).rstrip("/") + "/"
    new_norm = _normalize_path(new_prefix).rstrip("/") + "/"
    out: List[str] = []
    for item in images:
        normalized = _normalize_path(item)
        if normalized.startswith(old_norm):
            out.append(new_norm + normalized[len(old_norm) :])
        else:
            out.append(item)
    return out


def _parse_json_value(raw_value: Any) -> Any:
    if raw_value is None:
        return None
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except Exception:
            return raw_value
    return raw_value


def _dump_json_value(value: Any) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _rebase_string_path(raw_value: str, path_pairs: List[Tuple[str, str]]) -> Tuple[str, bool]:
    normalized = _normalize_path(raw_value)
    normalized_lower = normalized.lower()
    rebased = raw_value
    changed = False
    for old_path, new_path in path_pairs:
        old_norm = _normalize_path(old_path).rstrip("/")
        new_norm = _normalize_path(new_path).rstrip("/")
        if not old_norm:
            continue
        old_norm_lower = old_norm.lower()
        if normalized_lower == old_norm_lower:
            rebased = new_norm
            normalized = _normalize_path(rebased)
            normalized_lower = normalized.lower()
            changed = True
            continue
        old_prefix_lower = old_norm_lower + "/"
        if normalized_lower.startswith(old_prefix_lower):
            suffix = normalized[len(old_norm):]
            rebased = new_norm + suffix
            normalized = _normalize_path(rebased)
            normalized_lower = normalized.lower()
            changed = True
    return rebased, changed


def _rebase_json_paths(payload: Any, path_pairs: List[Tuple[str, str]]) -> Tuple[Any, bool]:
    if isinstance(payload, str):
        return _rebase_string_path(payload, path_pairs)
    if isinstance(payload, list):
        changed = False
        out = []
        for item in payload:
            rebased_item, item_changed = _rebase_json_paths(item, path_pairs)
            if item_changed:
                changed = True
            out.append(rebased_item)
        return out, changed
    if isinstance(payload, dict):
        changed = False
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            rebased_value, value_changed = _rebase_json_paths(value, path_pairs)
            if value_changed:
                changed = True
            out[key] = rebased_value
        return out, changed
    return payload, False


def _collect_legacy_run_dirs_from_json(payload: Any) -> Set[Path]:
    run_dirs: Set[Path] = set()
    if isinstance(payload, str):
        text = payload.strip()
        if "run_" not in text or "uploads" not in text:
            return run_dirs
        try:
            candidate = _resolve_abs_path(text)
        except Exception:
            return run_dirs
        legacy_run_dir = _detect_legacy_run_dir(candidate)
        if legacy_run_dir:
            run_dirs.add(legacy_run_dir)
        return run_dirs
    if isinstance(payload, list):
        for item in payload:
            run_dirs.update(_collect_legacy_run_dirs_from_json(item))
        return run_dirs
    if isinstance(payload, dict):
        for value in payload.values():
            run_dirs.update(_collect_legacy_run_dirs_from_json(value))
        return run_dirs
    return run_dirs


def _resolve_abs_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        return (BASE_DIR / candidate).resolve()
    return candidate.resolve()


def _detect_legacy_run_dir(image_path: Path) -> Optional[Path]:
    try:
        rel = image_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except Exception:
        return None
    if not rel.parts:
        return None
    top_name = rel.parts[0]
    if not str(top_name).startswith("run_"):
        return None
    return (OUTPUT_DIR / top_name).resolve()


def _rebase_representative_images(
    images: List[str],
    storage_uuid: str,
    dry_run: bool,
    moved_run_cache: Dict[str, Tuple[Path, bool]],
    summary: Dict[str, int],
) -> List[str]:
    rebased: List[str] = []
    user_videos_root = (OUTPUT_DIR / storage_uuid / "Videos").resolve()

    for raw in images:
        if not raw:
            rebased.append(raw)
            continue

        image_abs = _resolve_abs_path(raw)

        if _is_under(image_abs, user_videos_root):
            rebased.append(raw)
            continue

        legacy_run_dir = _detect_legacy_run_dir(image_abs)
        if not legacy_run_dir:
            rebased.append(raw)
            continue

        summary["frame_candidates"] += 1
        target_run_dir = (user_videos_root / legacy_run_dir.name).resolve()
        cache_key = str(legacy_run_dir)

        if cache_key not in moved_run_cache:
            moved, reason = _safe_move(legacy_run_dir, target_run_dir, dry_run=dry_run)
            moved_run_cache[cache_key] = (target_run_dir, moved)
            if moved:
                summary["frame_dirs_moved"] += 1
                print(f"[FRAME_DIR][OK] {legacy_run_dir} -> {target_run_dir} ({reason})")
            else:
                summary["frame_dirs_failed"] += 1
                print(f"[FRAME_DIR][FAIL] {legacy_run_dir} -> {target_run_dir} ({reason})")

        new_run_dir, moved = moved_run_cache[cache_key]
        if not moved:
            rebased.append(raw)
            continue

        try:
            rel_in_run = image_abs.resolve().relative_to(legacy_run_dir.resolve())
        except Exception:
            rebased.append(raw)
            continue

        new_image_abs = (new_run_dir / rel_in_run).resolve()
        new_image_raw = str(new_image_abs)
        if new_image_raw != raw:
            summary["frame_paths_rebased"] += 1
        rebased.append(new_image_raw)

    return rebased


def migrate(dry_run: bool = True, do_video: bool = True, do_pdf: bool = True) -> None:
    conn = _get_connection()
    if not conn:
        raise RuntimeError("Database is not configured")

    summary = {
        "video_candidates": 0,
        "video_moved": 0,
        "video_skipped": 0,
        "video_failed": 0,
        "frame_candidates": 0,
        "frame_dirs_moved": 0,
        "frame_dirs_failed": 0,
        "frame_paths_rebased": 0,
        "report_payload_rebased": 0,
        "pdf_candidates": 0,
        "pdf_moved": 0,
        "pdf_skipped": 0,
        "pdf_failed": 0,
    }

    with conn:
        _ensure_core_tables(conn)
        user_map = _load_user_storage_map(conn)
        old_videos_root = (OUTPUT_DIR / "videos").resolve()
        old_pdf_root = (OUTPUT_DIR / "reports_pdf").resolve()
        moved_run_cache: Dict[str, Tuple[Path, bool]] = {}

        if do_video:
            video_rows = _collect_video_reports(conn)
            for row in video_rows:
                summary["video_candidates"] += 1
                report_id = int(row["id"])
                user_id = int(row["user_id"] or 0)
                video_path = str(row.get("video_path") or "").strip()
                if not user_id or user_id not in user_map or not video_path:
                    summary["video_skipped"] += 1
                    continue

                storage_uuid = user_map[user_id]
                user_videos_root = (OUTPUT_DIR / storage_uuid / "Videos").resolve()
                src = _resolve_abs_path(video_path)
                final_video_path = video_path
                path_pairs: List[Tuple[str, str]] = []

                if _is_under(src, user_videos_root):
                    summary["video_skipped"] += 1
                elif _is_under(src, old_videos_root):
                    dst = _build_new_video_path(src, storage_uuid)
                    moved, reason = _safe_move(src, dst, dry_run=dry_run)
                    if not moved:
                        summary["video_failed"] += 1
                        print(f"[VIDEO][FAIL] report_id={report_id} src={src} dst={dst} reason={reason}")
                    else:
                        summary["video_moved"] += 1
                        final_video_path = str(dst)
                        path_pairs.append((str(src), str(dst)))
                        print(f"[VIDEO][OK] report_id={report_id} {src} -> {dst} ({reason})")
                else:
                    summary["video_skipped"] += 1

                images = _parse_images(row.get("representative_images"))
                region_info_payload = _parse_json_value(row.get("region_info"))
                report_json_payload = _parse_json_value(row.get("report_json"))

                legacy_run_dirs: Set[Path] = set()
                legacy_run_dirs.update(_collect_legacy_run_dirs_from_json(images))
                legacy_run_dirs.update(_collect_legacy_run_dirs_from_json(region_info_payload))
                legacy_run_dirs.update(_collect_legacy_run_dirs_from_json(report_json_payload))

                for legacy_run_dir in sorted(legacy_run_dirs, key=lambda item: str(item)):
                    target_run_dir = (user_videos_root / legacy_run_dir.name).resolve()
                    cache_key = str(legacy_run_dir)
                    if cache_key not in moved_run_cache:
                        moved, reason = _safe_move(legacy_run_dir, target_run_dir, dry_run=dry_run)
                        moved_run_cache[cache_key] = (target_run_dir, moved)
                        if moved:
                            summary["frame_dirs_moved"] += 1
                            print(f"[FRAME_DIR][OK] {legacy_run_dir} -> {target_run_dir} ({reason})")
                        else:
                            summary["frame_dirs_failed"] += 1
                            print(f"[FRAME_DIR][FAIL] {legacy_run_dir} -> {target_run_dir} ({reason})")
                    new_run_dir, moved = moved_run_cache[cache_key]
                    if moved:
                        path_pairs.append((str(legacy_run_dir), str(new_run_dir)))

                replaced_images = _rebase_representative_images(
                    images,
                    storage_uuid=storage_uuid,
                    dry_run=dry_run,
                    moved_run_cache=moved_run_cache,
                    summary=summary,
                )
                rebased_region_info, region_info_changed = _rebase_json_paths(
                    region_info_payload, path_pairs
                )
                rebased_report_json, report_json_changed = _rebase_json_paths(
                    report_json_payload, path_pairs
                )
                if region_info_changed or report_json_changed:
                    summary["report_payload_rebased"] += 1

                should_update_video_path = final_video_path != video_path
                should_update_images = replaced_images != images
                should_update_region_info = region_info_changed
                should_update_report_json = report_json_changed

                if (
                    should_update_video_path
                    or should_update_images
                    or should_update_region_info
                    or should_update_report_json
                ) and not dry_run:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE reports "
                            "SET video_path=%s, representative_images=%s, region_info=%s, report_json=%s "
                            "WHERE id=%s",
                            (
                                final_video_path if should_update_video_path else video_path,
                                _dump_images(replaced_images),
                                _dump_json_value(
                                    rebased_region_info
                                    if should_update_region_info
                                    else region_info_payload
                                ),
                                _dump_json_value(
                                    rebased_report_json
                                    if should_update_report_json
                                    else report_json_payload
                                ),
                                report_id,
                            ),
                        )
                        print(
                            "[REPORT][UPDATE] "
                            f"report_id={report_id} "
                            f"video_path={should_update_video_path} "
                            f"images={should_update_images} "
                            f"region_info={should_update_region_info} "
                            f"report_json={should_update_report_json}"
                        )

        if do_pdf:
            pdf_rows = _collect_pdf_reports(conn)
            for row in pdf_rows:
                summary["pdf_candidates"] += 1
                report_id = int(row["id"])
                user_id = int(row["user_id"] or 0)
                source_path = str(row.get("source_path") or "").strip()
                if not user_id or user_id not in user_map or not source_path:
                    summary["pdf_skipped"] += 1
                    continue

                src = _resolve_abs_path(source_path)

                storage_uuid = user_map[user_id]
                if _is_under(src, OUTPUT_DIR / storage_uuid / "PDF"):
                    summary["pdf_skipped"] += 1
                    continue

                if not _is_under(src, old_pdf_root):
                    summary["pdf_skipped"] += 1
                    continue

                dst = _build_new_pdf_path(src, storage_uuid)
                moved, reason = _safe_move(src, dst, dry_run=dry_run)
                if not moved:
                    summary["pdf_failed"] += 1
                    print(f"[PDF][FAIL] report_id={report_id} src={src} dst={dst} reason={reason}")
                    continue

                if not dry_run:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE reports SET source_path=%s WHERE id=%s",
                            (str(dst), report_id),
                        )

                summary["pdf_moved"] += 1
                print(f"[PDF][OK] report_id={report_id} {src} -> {dst} ({reason})")

    print("\n=== Migration Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"mode: {'dry-run' if dry_run else 'apply'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate historical uploads to per-user storage_uuid folders")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration changes. Default is dry-run.",
    )
    parser.add_argument(
        "--only-pdf",
        action="store_true",
        help="Only migrate legacy PDF uploads.",
    )
    args = parser.parse_args()
    migrate(
        dry_run=not args.apply,
        do_video=not args.only_pdf,
        do_pdf=True,
    )


if __name__ == "__main__":
    main()
