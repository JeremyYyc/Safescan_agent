import asyncio
import hashlib
from queue import Full, Queue
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from minio.error import S3Error
from sqlalchemy.orm import Session

from .auth import Principal
from .clients import MaintenanceClient, PropertyLeasingClient
from .config import Settings
from .errors import error, hidden_not_found
from .repository import ReportRepository, digest
from .storage import asset_ref, minio_client


class _QueueReader:
    def __init__(self, queue: Queue) -> None:
        self.queue = queue
        self.buffer = b""

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self.buffer) < size:
            chunk = self.queue.get()
            if chunk is None:
                break
            self.buffer += chunk
        if size < 0:
            value, self.buffer = self.buffer, b""
        else:
            value, self.buffer = self.buffer[:size], self.buffer[size:]
        return value


class ReportService:
    def __init__(self, db: Session, leasing: PropertyLeasingClient, settings: Settings,
                 maintenance: MaintenanceClient | None = None) -> None:
        self.db = db
        self.repo = ReportRepository(db)
        self.leasing = leasing
        self.settings = settings
        self.maintenance = maintenance or MaintenanceClient(settings)

    def _creation_binding(self, actor: Principal, property_id: UUID) -> UUID | None:
        if actor.account_type == "customer":
            if actor.customer_status != "tenant" or not actor.has("report:self:create"):
                raise error(403, "report_generation_not_allowed", "Only a current tenant may create a report",
                            required_lease_status="active")
            access = self.leasing.property_access(actor, property_id, "report:create")
            if not access.get("allowed") or not access.get("active_lease_id"):
                raise hidden_not_found()
            return UUID(access["active_lease_id"])
        if actor.has("report:generate_all"):
            pass
        elif not actor.has("report:generate_assigned"):
            raise error(403, "report_generation_not_allowed", "Staff role cannot create reports")
        access = self.leasing.property_access(actor, property_id, "report:create")
        if not access.get("allowed"):
            raise hidden_not_found()
        return UUID(access["active_lease_id"]) if access.get("active_lease_id") else None

    def create_report(self, actor: Principal, property_id: UUID, title: str | None,
                      key: UUID, correlation_id: UUID) -> dict:
        lease_id = self._creation_binding(actor, property_id)
        return self.repo.create_report(
            actor.subject_id, actor.account_type, property_id, lease_id,
            (title or "Home Safety Inspection").strip() or "Home Safety Inspection",
            key, correlation_id, self.settings.pipeline_version,
        )

    def _authorize_report(self, actor: Principal, report: dict, *, lease_context: UUID | None = None,
                          write: bool = False) -> None:
        property_id = UUID(str(report["property_id"]))
        if actor.account_type == "staff":
            if write:
                permitted = actor.has("report:generate_all") or actor.has("report:generate_assigned")
            else:
                permitted = actor.has("report:read_all") or actor.has("report:read_assigned")
            # Maintainer's work-context scope never grants full report access.
            if not permitted:
                raise hidden_not_found()
            if not self.leasing.property_access(actor, property_id, "report:write" if write else "report:read").get("allowed"):
                raise hidden_not_found()
            return
        source_lease = report.get("source_lease_id")
        if not source_lease:
            raise hidden_not_found()
        if lease_context:
            access = self.leasing.lease_access(actor, lease_context, property_id, "report:read_history")
            if not access.get("allowed") or access.get("status") not in {"ended", "terminated", "active"}:
                raise hidden_not_found()
            if UUID(str(source_lease)) != lease_context:
                raise hidden_not_found()
            if write:
                raise hidden_not_found()
            return
        if actor.customer_status != "tenant" or not actor.has("report:self:read"):
            raise hidden_not_found()
        access = self.leasing.property_access(actor, property_id, "report:read")
        if not access.get("allowed") or str(access.get("active_lease_id")) != str(source_lease):
            raise hidden_not_found()
        if write and report["created_by_subject_id"] != actor.subject_id:
            raise hidden_not_found()

    def report(self, actor: Principal, report_id: UUID, lease_context: UUID | None = None,
               write: bool = False) -> dict:
        report = self.repo.get_report(report_id)
        if not report:
            raise hidden_not_found()
        self._authorize_report(actor, report, lease_context=lease_context, write=write)
        return report

    def reports(self, actor: Principal, property_id: UUID, lease_context: UUID | None = None) -> list[dict]:
        if actor.account_type == "staff":
            if not (actor.has("report:read_all") or actor.has("report:read_assigned")):
                raise hidden_not_found()
            if not self.leasing.property_access(actor, property_id, "report:read").get("allowed"):
                raise hidden_not_found()
            return self.repo.list_reports(property_id)
        if lease_context:
            access = self.leasing.lease_access(actor, lease_context, property_id, "report:read_history")
            if not access.get("allowed") or access.get("status") not in {"ended", "terminated"}:
                raise hidden_not_found()
            return self.repo.list_reports(property_id, lease_context)
        if actor.customer_status != "tenant" or not actor.has("report:self:read"):
            raise hidden_not_found()
        access = self.leasing.property_access(actor, property_id, "report:read")
        if not access.get("allowed") or not access.get("active_lease_id"):
            raise hidden_not_found()
        return self.repo.list_reports(property_id, UUID(access["active_lease_id"]))

    async def upload_video(self, actor: Principal, report_id: UUID, request: Request,
                           filename: str, declared_sha: str | None, key: UUID) -> dict:
        report = self.report(actor, report_id, write=True)
        mime = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if not mime.startswith("video/"):
            raise error(415, "unsupported_media_type", "Only video uploads are accepted")
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.settings.max_upload_bytes:
            raise error(413, "payload_too_large", "Video exceeds configured upload limit")
        request_digest = digest({"report_id": report_id, "filename": filename, "mime": mime,
                                 "length": content_length, "sha256": declared_sha})
        replay = self.repo.find_file_replay(actor.subject_id, key, request_digest)
        if replay:
            return replay

        public_id = uuid4()
        bucket = self.settings.minio_media_bucket
        object_key = f"reports/{report_id.hex}/input/{public_id.hex}"
        client = minio_client(
            self.settings.minio_endpoint, self.settings.minio_access_key.get_secret_value(),
            self.settings.minio_secret_key.get_secret_value(), self.settings.minio_secure,
        )
        queue: Queue = Queue(maxsize=4)
        reader = _QueueReader(queue)
        upload = asyncio.create_task(asyncio.to_thread(
            client.put_object, bucket, object_key, reader, -1,
            part_size=max(5 * 1024 * 1024, self.settings.upload_chunk_bytes), content_type=mime,
        ))
        hasher = hashlib.sha256()
        size = 0

        async def enqueue(value: bytes | None) -> None:
            while True:
                if upload.done():
                    await upload
                try:
                    queue.put_nowait(value)
                    return
                except Full:
                    await asyncio.sleep(0.01)

        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > self.settings.max_upload_bytes:
                    raise error(413, "payload_too_large", "Video exceeds configured upload limit")
                hasher.update(chunk)
                await enqueue(chunk)
            await enqueue(None)
            await upload
            actual_sha = hasher.hexdigest()
            if declared_sha and declared_sha.lower().removeprefix("sha256:") != actual_sha:
                raise error(422, "validation_failed", "Content digest does not match",
                            fields=[{"field": "X-Content-SHA256", "reason": "digest_mismatch"}])
            saved = self.repo.save_uploaded_file(
                report_internal_id=report["id"], actor=actor.subject_id, public_id=public_id,
                bucket=bucket, object_key=object_key, original_name=filename, mime_type=mime,
                size=size, sha256=actual_sha, key=key, request_digest=request_digest,
            )
            if saved.pop("_discard_object", False):
                client.remove_object(bucket, object_key)
            return saved
        except BaseException:
            if not upload.done():
                try:
                    await enqueue(None)
                except Exception:
                    pass
            try:
                await upload
            except Exception:
                pass
            try:
                client.remove_object(bucket, object_key)
            except S3Error:
                pass
            raise

    def create_job(self, actor: Principal, report_id: UUID, file_id: UUID,
                   attributes: dict, key: UUID) -> dict:
        report = self.report(actor, report_id, write=True)
        return self.repo.create_job(
            report=report, actor=actor.subject_id, file_id=file_id, attributes=attributes,
            key=key, pipeline_version=self.settings.pipeline_version,
            max_attempts=self.settings.max_attempts,
        )

    def job(self, actor: Principal, job_id: UUID, lease_context: UUID | None = None) -> dict:
        job = self.repo.get_job(job_id)
        if not job:
            raise hidden_not_found()
        report = self.repo.get_report(job["report_public_id"])
        if not report:
            raise hidden_not_found()
        self._authorize_report(actor, report, lease_context=lease_context)
        return job

    def work_context(self, actor: Principal, report_id: UUID, order_id: UUID) -> dict:
        if actor.account_type != "staff" or actor.role != "maintainer" or not actor.has("report:read_work_context"):
            raise hidden_not_found()
        report = self.repo.get_report(report_id)
        if not report:
            raise hidden_not_found()
        access = self.maintenance.order_access(actor, order_id, report_id)
        if not access.get("allowed") or str(access.get("property_id")) != str(report["property_id"]):
            raise hidden_not_found()
        payload = report.get("report_payload") or {}
        regions = []
        for value in payload.get("regions", []) if isinstance(payload, dict) else []:
            if not isinstance(value, dict):
                continue
            regions.append({
                key: value[key] for key in (
                    "regionName", "generalHazards", "specificHazards",
                    "recommendations", "evidenceImages",
                ) if key in value
            })
        return {
            "id": report["public_id"], "property_id": report["property_id"],
            "title": report["title"], "status": report["status"], "regions": regions,
        }
