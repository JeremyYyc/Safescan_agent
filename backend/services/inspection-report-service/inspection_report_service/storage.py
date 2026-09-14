from contextlib import contextmanager
from functools import lru_cache
from io import BytesIO
import hashlib
import os
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from minio import Minio
import sqlalchemy as sa

from .config import Settings
from .database import get_session_factory


def asset_uuid(ref: str) -> UUID:
    value = str(ref).removeprefix("/api/assets/")
    return UUID(value)


def asset_ref(value: UUID) -> str:
    return f"/api/assets/{value.hex}"


@lru_cache(maxsize=4)
def minio_client(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


class PipelineStorage:
    """Legacy media-tool storage adapter scoped to one pre-authorized report."""

    def __init__(self, settings: Settings, report_id: int, report_public_id: UUID, actor_subject_id: UUID) -> None:
        self.settings = settings
        self.report_id = report_id
        self.report_public_id = report_public_id
        self.actor_subject_id = actor_subject_id
        self.client = minio_client(
            settings.minio_endpoint, settings.minio_access_key.get_secret_value(),
            settings.minio_secret_key.get_secret_value(), settings.minio_secure,
        )

    def record(self, ref: str) -> dict:
        with get_session_factory()() as db:
            row = db.execute(sa.text(
                "SELECT * FROM inspection_report.files WHERE public_id=:id AND report_id=:report "
                "AND status='ready' AND scan_status='clean'"
            ), {"id": asset_uuid(ref), "report": self.report_id}).mappings().first()
            if not row:
                raise FileNotFoundError("Asset not available")
            return dict(row)

    def put(self, data: bytes, mime: str, *, category: str = "derived", name: str = "") -> str:
        public_id = uuid4()
        bucket = self.settings.minio_derived_bucket if category == "derived" else self.settings.minio_media_bucket
        purpose = "evidence_image" if category == "derived" else "input_video"
        object_key = f"reports/{self.report_public_id.hex}/{public_id.hex}"
        self.client.put_object(bucket, object_key, BytesIO(data), len(data), content_type=mime)
        try:
            with get_session_factory()() as db, db.begin():
                db.execute(sa.text(
                    "INSERT INTO inspection_report.files "
                    "(public_id,created_by_subject_id,purpose,bucket,object_key,original_name,mime_type,file_size,sha256,"
                    "status,scan_status,report_id) VALUES (:public,:actor,:purpose,:bucket,:object,:name,:mime,:size,:sha,"
                    "'ready','clean',:report)"
                ), {"public": public_id, "actor": self.actor_subject_id, "purpose": purpose,
                    "bucket": bucket, "object": object_key, "name": name[:255], "mime": mime,
                    "size": len(data), "sha": hashlib.sha256(data).hexdigest(), "report": self.report_id})
        except BaseException:
            self.client.remove_object(bucket, object_key)
            raise
        return asset_ref(public_id)

    def put_file(self, path: str, mime: str, *, category: str = "derived", name: str = "") -> str:
        with Path(path).open("rb") as handle:
            return self.put(handle.read(), mime, category=category, name=name)

    @contextmanager
    def local_copy(self, ref: str, *, maximum: int | None = None):
        row = self.record(ref)
        limit = maximum or self.settings.max_upload_bytes
        if row["file_size"] is not None and row["file_size"] > limit:
            raise ValueError("Asset exceeds configured limit")
        descriptor, path = tempfile.mkstemp(prefix="safescan-report-", suffix=Path(row["original_name"] or "").suffix)
        response = None
        total = 0
        try:
            response = self.client.get_object(row["bucket"], row["object_key"])
            with os.fdopen(descriptor, "wb") as output:
                descriptor = -1
                while True:
                    chunk = response.read(self.settings.upload_chunk_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("Asset exceeds configured limit")
                    output.write(chunk)
            yield path
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if response is not None:
                response.close()
                response.release_conn()
            Path(path).unlink(missing_ok=True)

    def read(self, ref: str) -> bytes:
        row = self.record(ref)
        response = self.client.get_object(row["bucket"], row["object_key"])
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def replace(self, ref: str, data: bytes, mime: str = "image/jpeg") -> None:
        row = self.record(ref)
        self.client.put_object(row["bucket"], row["object_key"], BytesIO(data), len(data), content_type=mime)
        with get_session_factory()() as db, db.begin():
            db.execute(sa.text(
                "UPDATE inspection_report.files SET file_size=:size,sha256=:sha,mime_type=:mime,updated_at=NOW() WHERE id=:id"
            ), {"size": len(data), "sha": hashlib.sha256(data).hexdigest(), "mime": mime, "id": row["id"]})

    def remove_unreferenced(self, ref: str) -> bool:
        try:
            row = self.record(ref)
        except FileNotFoundError:
            return False
        with get_session_factory()() as db, db.begin():
            count = db.execute(sa.text(
                "SELECT count(*) FROM inspection_report.report_assets WHERE file_id=:id"
            ), {"id": row["id"]}).scalar_one()
            if count or row["purpose"] == "input_video":
                return False
            self.client.remove_object(row["bucket"], row["object_key"])
            db.execute(sa.text("DELETE FROM inspection_report.files WHERE id=:id"), {"id": row["id"]})
        return True
