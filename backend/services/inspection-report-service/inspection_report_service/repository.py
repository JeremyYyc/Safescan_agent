import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from .errors import error, hidden_not_found


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _mapping(result) -> dict | None:
    row = result.mappings().first()
    return dict(row) if row else None


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.db = session

    def _prepare_write(self) -> None:
        # Read authorization queries use SQLAlchemy's implicit transaction. End that
        # snapshot before starting the short command transaction.
        if self.db.in_transaction():
            self.db.rollback()

    def _idempotent(self, actor: UUID, operation: str, key: UUID, request_digest: str) -> dict | None:
        row = _mapping(self.db.execute(sa.text(
            "SELECT request_digest,resource_type,resource_id,response_status "
            "FROM inspection_report.report_idempotency_records "
            "WHERE actor_subject_id=:actor AND operation=:operation AND idempotency_key=:key"
        ), {"actor": actor, "operation": operation, "key": key}))
        if row and row["request_digest"] != request_digest:
            raise error(409, "idempotency_conflict", "Idempotency key was used for a different request", operation=operation)
        return row

    def _lock_idempotency(self, actor: UUID, operation: str, key: UUID) -> None:
        self.db.execute(sa.text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:value,0))"
        ), {"value": f"inspection-report:{actor}:{operation}:{key}"})

    def _save_idempotent(self, actor: UUID, operation: str, key: UUID, request_digest: str,
                         resource_type: str, resource_id: UUID, response_status: int) -> None:
        self.db.execute(sa.text(
            "INSERT INTO inspection_report.report_idempotency_records "
            "(actor_subject_id,operation,idempotency_key,request_digest,resource_type,resource_id,response_status) "
            "VALUES (:actor,:operation,:key,:digest,:type,:resource,:status)"
        ), {"actor": actor, "operation": operation, "key": key, "digest": request_digest,
            "type": resource_type, "resource": resource_id, "status": response_status})

    def _audit(self, report_id: int, actor: UUID, event_type: str, correlation_id: UUID,
               details: dict | None = None) -> None:
        self.db.execute(sa.text(
            "INSERT INTO inspection_report.report_audit_events "
            "(report_id,actor_subject_id,event_type,correlation_id,details_redacted) "
            "VALUES (:report,:actor,:event,:correlation,CAST(:details AS jsonb))"
        ), {"report": report_id, "actor": actor, "event": event_type,
            "correlation": correlation_id, "details": json.dumps(details or {})})

    def get_report(self, report_id: UUID, *, lock: bool = False) -> dict | None:
        suffix = " FOR UPDATE OF r" if lock else ""
        return _mapping(self.db.execute(sa.text(
            "SELECT r.*,a.region_info,a.report_payload,a.validation_passed,a.validation_errors "
            "FROM inspection_report.reports r LEFT JOIN inspection_report.report_analysis a ON a.report_id=r.id "
            "WHERE r.public_id=:id AND r.is_formal AND r.status<>'deleted'" + suffix
        ), {"id": report_id}))

    def create_report(self, actor: UUID, account_type: str, property_id: UUID,
                      source_lease_id: UUID | None, title: str, key: UUID,
                      correlation_id: UUID, pipeline_version: str) -> dict:
        request_digest = digest({"property_id": property_id, "source_lease_id": source_lease_id,
                                 "account_type": account_type, "title": title})
        self._prepare_write()
        with self.db.begin():
            self._lock_idempotency(actor, "create_report", key)
            replay = self._idempotent(actor, "create_report", key, request_digest)
            if replay:
                report = self.get_report(replay["resource_id"])
                if not report:
                    raise hidden_not_found()
                return report
            public_id = uuid4()
            row = _mapping(self.db.execute(sa.text(
                "INSERT INTO inspection_report.reports "
                "(public_id,property_id,source_lease_id,created_by_subject_id,created_by_account_type,"
                "is_formal,report_kind,source,title,status,schema_version,pipeline_version,version) "
                "VALUES (:public,:property,:lease,:actor,:account,true,'analysis','video_analysis',:title,'draft',1,:pipeline,1) "
                "RETURNING *"
            ), {"public": public_id, "property": property_id, "lease": source_lease_id,
                "actor": actor, "account": account_type, "title": title, "pipeline": pipeline_version}))
            self.db.execute(sa.text(
                "UPDATE inspection_report.reports SET legacy_context_id=id WHERE id=:id"
            ), {"id": row["id"]})
            self._audit(row["id"], actor, "report.created", correlation_id, {
                "property_id": str(property_id),
                "source_lease_id": str(source_lease_id) if source_lease_id else None,
            })
            self._save_idempotent(actor, "create_report", key, request_digest, "report", public_id, 201)
        return self.get_report(public_id)

    def list_reports(self, property_id: UUID, source_lease_id: UUID | None = None) -> list[dict]:
        query = (
            "SELECT r.*,a.validation_passed FROM inspection_report.reports r "
            "LEFT JOIN inspection_report.report_analysis a ON a.report_id=r.id "
            "WHERE r.is_formal AND r.property_id=:property AND r.status<>'deleted'"
        )
        params: dict[str, Any] = {"property": property_id}
        if source_lease_id:
            query += " AND r.source_lease_id=:lease"
            params["lease"] = source_lease_id
        query += " ORDER BY r.created_at DESC,r.id DESC"
        return [dict(row) for row in self.db.execute(sa.text(query), params).mappings()]

    def evidence_ids(self, report_internal_id: int) -> list[UUID]:
        return list(self.db.scalars(sa.text(
            "SELECT f.public_id FROM inspection_report.report_assets a "
            "JOIN inspection_report.files f ON f.id=a.file_id "
            "WHERE a.report_id=:report AND a.asset_kind='evidence_image' ORDER BY a.sort_order,a.id"
        ), {"report": report_internal_id}))

    def get_file(self, file_id: UUID) -> dict | None:
        return _mapping(self.db.execute(sa.text(
            "SELECT f.*,r.public_id AS report_public_id,r.property_id,r.source_lease_id,"
            "r.created_by_account_type FROM inspection_report.files f "
            "LEFT JOIN inspection_report.reports r ON r.id=f.report_id WHERE f.public_id=:id"
        ), {"id": file_id}))

    def find_file_replay(self, actor: UUID, key: UUID, request_digest: str) -> dict | None:
        row = _mapping(self.db.execute(sa.text(
            "SELECT * FROM inspection_report.files WHERE created_by_subject_id=:actor AND idempotency_key=:key"
        ), {"actor": actor, "key": key}))
        if row and row["request_digest"] != request_digest:
            raise error(409, "idempotency_conflict", "Idempotency key was used for a different upload", operation="upload_video")
        return row

    def save_uploaded_file(self, *, report_internal_id: int, actor: UUID, public_id: UUID,
                           bucket: str, object_key: str, original_name: str, mime_type: str,
                           size: int, sha256: str, key: UUID, request_digest: str) -> dict:
        self._prepare_write()
        with self.db.begin():
            row = _mapping(self.db.execute(sa.text(
                "INSERT INTO inspection_report.files "
                "(public_id,created_by_subject_id,purpose,bucket,object_key,original_name,mime_type,file_size,sha256,"
                "status,scan_status,report_id,idempotency_key,request_digest) "
                "VALUES (:public,:actor,'input_video',:bucket,:object,:name,:mime,:size,:sha,'ready','clean',:report,:key,:digest) "
                "ON CONFLICT (created_by_subject_id,idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING "
                "RETURNING *"
            ), {"public": public_id, "actor": actor, "bucket": bucket, "object": object_key,
                "name": original_name[:255], "mime": mime_type, "size": size, "sha": sha256,
                "report": report_internal_id, "key": key, "digest": request_digest}))
            if not row:
                row = _mapping(self.db.execute(sa.text(
                    "SELECT * FROM inspection_report.files "
                    "WHERE created_by_subject_id=:actor AND idempotency_key=:key"
                ), {"actor": actor, "key": key}))
                if not row or row["request_digest"] != request_digest:
                    raise error(409, "idempotency_conflict",
                                "Idempotency key was used for a different upload",
                                operation="upload_video")
                row["_discard_object"] = True
        return row

    def create_job(self, *, report: dict, actor: UUID, file_id: UUID, attributes: dict,
                   key: UUID, pipeline_version: str, max_attempts: int) -> dict:
        request_digest = digest({"report_id": report["public_id"], "input_file_id": file_id, "attributes": attributes})
        self._prepare_write()
        with self.db.begin():
            self._lock_idempotency(actor, "create_report_job", key)
            replay = self._idempotent(actor, "create_report_job", key, request_digest)
            if replay:
                job = self.get_job(replay["resource_id"])
                if not job:
                    raise hidden_not_found()
                return job
            locked = self.get_report(report["public_id"], lock=True)
            file_row = self.get_file(file_id)
            if not locked or not file_row or file_row["status"] != "ready" or file_row["report_id"] != locked["id"]:
                raise error(409, "file_not_ready", "Input file is not ready", file_status=file_row["status"] if file_row else "missing")
            if locked["status"] not in {"draft", "failed"}:
                raise error(409, "active_job_exists", "Report already has an active or completed job")
            public_id = uuid4()
            job = _mapping(self.db.execute(sa.text(
                "INSERT INTO inspection_report.report_jobs "
                "(public_id,requested_by_subject_id,source_service,job_type,input_file_id,report_id,queue,priority,status,"
                "attempt,max_attempts,available_at,idempotency_key,request_digest,pipeline_version,input_payload) "
                "VALUES (:public,:actor,'portal','video_analysis',:file,:report,'report-analysis',0,'queued',0,:max,NOW(),"
                ":key,:digest,:pipeline,CAST(:payload AS jsonb)) RETURNING *"
            ), {"public": public_id, "actor": actor, "file": file_row["id"], "report": locked["id"],
                "max": max_attempts, "key": key, "digest": request_digest, "pipeline": pipeline_version,
                "payload": json.dumps({"attributes": attributes})}))
            self.db.execute(sa.text(
                "UPDATE inspection_report.reports SET status='processing',version=version+1,updated_at=NOW() WHERE id=:id"
            ), {"id": locked["id"]})
            self._append_event(job["id"], "job.created", "queued", 0, "Report job queued", {})
            self._audit(locked["id"], actor, "report.job_created", public_id,
                        {"job_id": str(public_id)})
            self._save_idempotent(actor, "create_report_job", key, request_digest, "job", public_id, 202)
        return self.get_job(public_id)

    def _append_event(self, job_id: int, event_type: str, stage: str, progress: float | None,
                      message: str | None, payload: dict) -> int:
        sequence = self.db.execute(sa.text(
            "UPDATE inspection_report.report_jobs SET next_event_sequence=next_event_sequence+1,updated_at=NOW() "
            "WHERE id=:job RETURNING next_event_sequence-1"
        ), {"job": job_id}).scalar_one()
        self.db.execute(sa.text(
            "INSERT INTO inspection_report.report_job_events "
            "(job_id,sequence_no,event_type,stage,progress_percent,message,payload_redacted) "
            "VALUES (:job,:sequence,:type,:stage,:progress,:message,CAST(:payload AS jsonb))"
        ), {"job": job_id, "sequence": sequence, "type": event_type, "stage": stage,
            "progress": progress, "message": message, "payload": json.dumps(payload)})
        return int(sequence)

    def append_event(self, *args, **kwargs) -> int:
        self._prepare_write()
        with self.db.begin():
            return self._append_event(*args, **kwargs)

    def get_job(self, job_id: UUID) -> dict | None:
        return _mapping(self.db.execute(sa.text(
            "SELECT j.*,r.public_id AS report_public_id,r.property_id,r.source_lease_id,"
            "r.created_by_account_type,r.created_by_subject_id AS report_creator,f.public_id AS file_public_id,"
            "f.bucket,f.object_key,f.file_size,f.mime_type,f.original_name,r.status AS report_status,"
            "a.report_payload,a.region_info,a.validation_passed AS report_validation_passed "
            "FROM inspection_report.report_jobs j JOIN inspection_report.reports r ON r.id=j.report_id "
            "LEFT JOIN inspection_report.files f ON f.id=j.input_file_id "
            "LEFT JOIN inspection_report.report_analysis a ON a.report_id=r.id WHERE j.public_id=:id"
        ), {"id": job_id}))

    def job_events(self, internal_id: int, after: int = 0) -> list[dict]:
        return [dict(row) for row in self.db.execute(sa.text(
            "SELECT sequence_no,event_type,stage,progress_percent,message,payload_redacted,created_at "
            "FROM inspection_report.report_job_events WHERE job_id=:job AND sequence_no>:after ORDER BY sequence_no"
        ), {"job": internal_id, "after": after}).mappings()]

    def job_steps(self, internal_id: int) -> list[dict]:
        return [dict(row) for row in self.db.execute(sa.text(
            "SELECT step_name,attempt,status,started_at,finished_at,metrics,error_code "
            "FROM inspection_report.report_job_steps WHERE job_id=:job ORDER BY attempt,id"
        ), {"job": internal_id}).mappings()]

    def request_cancel(self, job: dict, actor: UUID, reason: str, key: UUID,
                       correlation_id: UUID) -> dict:
        request_digest = digest({"job_id": job["public_id"], "reason": reason})
        self._prepare_write()
        with self.db.begin():
            self._lock_idempotency(actor, "cancel_report_job", key)
            replay = self._idempotent(actor, "cancel_report_job", key, request_digest)
            if replay:
                return self.get_job(job["public_id"])
            current = self.get_job(job["public_id"])
            if not current:
                raise hidden_not_found()
            if current["status"] in {"completed", "failed", "cancelled"}:
                raise error(409, "state_conflict", "Terminal report job cannot be cancelled")
            immediate = current["status"] in {"queued", "retry_wait"}
            self.db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET cancel_requested_at=NOW(),cancel_reason=:reason,"
                "status=CASE WHEN :immediate THEN 'cancelled' ELSE status END,"
                "finished_at=CASE WHEN :immediate THEN NOW() ELSE finished_at END,updated_at=NOW() WHERE id=:id"
            ), {"reason": reason, "immediate": immediate, "id": current["id"]})
            if immediate:
                self.db.execute(sa.text(
                    "UPDATE inspection_report.reports SET status='failed',version=version+1,updated_at=NOW() WHERE id=:id"
                ), {"id": current["report_id"]})
            self._append_event(current["id"], "job.cancelled" if immediate else "job.cancel_requested",
                               "cancelled" if immediate else "workflow", current["progress_percent"],
                               "Cancellation requested", {"correlation_id": str(correlation_id)})
            self._audit(current["report_id"], actor,
                        "report.job_cancelled" if immediate else "report.job_cancel_requested",
                        correlation_id, {"job_id": str(current["public_id"])})
            self._save_idempotent(actor, "cancel_report_job", key, request_digest, "job", current["public_id"], 202)
        return self.get_job(job["public_id"])

    def is_cancel_requested(self, internal_id: int) -> bool:
        return bool(self.db.execute(sa.text(
            "SELECT cancel_requested_at IS NOT NULL FROM inspection_report.report_jobs WHERE id=:id"
        ), {"id": internal_id}).scalar())

    def recover_stale(self) -> int:
        self._prepare_write()
        rows = list(self.db.execute(sa.text(
            "UPDATE inspection_report.report_jobs j SET status=CASE "
            "WHEN r.status='active' OR j.attempt<j.max_attempts THEN 'retry_wait' ELSE 'failed' END,"
            "attempt=CASE WHEN r.status='active' THEN GREATEST(j.attempt-1,0) ELSE j.attempt END,"
            "available_at=NOW(),worker_id=NULL,lease_until=NULL,error_code='worker_lease_expired',"
            "finished_at=CASE WHEN r.status<>'active' AND j.attempt>=j.max_attempts THEN NOW() ELSE NULL END,"
            "updated_at=NOW() FROM inspection_report.reports r "
            "WHERE j.report_id=r.id AND j.status='running' AND j.lease_until<NOW() "
            "RETURNING j.id,j.status,j.report_id"
        )).mappings())
        for row in rows:
            self._append_event(row["id"], "job.retry_wait" if row["status"] == "retry_wait" else "job.failed",
                               row["status"], None, "Worker lease expired", {"code": "worker_lease_expired"})
            if row["status"] == "failed":
                self.db.execute(sa.text("UPDATE inspection_report.reports SET status='failed',version=version+1,updated_at=NOW() WHERE id=:id"), {"id": row["report_id"]})
        self.db.commit()
        return len(rows)

    def claim(self, worker_id: str, lease_seconds: int) -> dict | None:
        self._prepare_write()
        with self.db.begin():
            row = _mapping(self.db.execute(sa.text(
                "WITH candidate AS (SELECT id FROM inspection_report.report_jobs "
                "WHERE status IN ('queued','retry_wait') AND available_at<=NOW() AND cancel_requested_at IS NULL "
                "ORDER BY priority DESC,available_at,id FOR UPDATE SKIP LOCKED LIMIT 1) "
                "UPDATE inspection_report.report_jobs j SET status='running',attempt=j.attempt+1,worker_id=:worker,"
                "lease_until=NOW()+make_interval(secs=>:lease),heartbeat_at=NOW(),updated_at=NOW() "
                "FROM candidate WHERE j.id=candidate.id RETURNING j.public_id"
            ), {"worker": worker_id, "lease": lease_seconds}))
            if not row:
                return None
            job = self.get_job(row["public_id"])
            self._append_event(job["id"], "job.started", "workflow", 1, "Report processing started", {})
            return job

    def heartbeat(self, internal_id: int, worker_id: str, lease_seconds: int,
                  progress: float | None = None) -> bool:
        self._prepare_write()
        with self.db.begin():
            result = self.db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET heartbeat_at=NOW(),"
                "lease_until=NOW()+make_interval(secs=>:lease),progress_percent=COALESCE(:progress,progress_percent),"
                "updated_at=NOW() WHERE id=:id AND worker_id=:worker AND status='running'"
            ), {"lease": lease_seconds, "progress": progress, "id": internal_id, "worker": worker_id})
            return result.rowcount == 1

    def record_step(self, job_id: int, attempt: int, event: str, metrics: dict) -> None:
        suffix = "_start" if event.endswith("_start") else "_complete" if event.endswith("_complete") else ""
        if not suffix:
            return
        name = event[:-len(suffix)]
        status = "running" if suffix == "_start" else "completed"
        self._prepare_write()
        with self.db.begin():
            self.db.execute(sa.text(
                "INSERT INTO inspection_report.report_job_steps "
                "(job_id,step_name,attempt,status,started_at,finished_at,metrics) "
                "VALUES (:job,:name,:attempt,:status,NOW(),CASE WHEN :status='completed' THEN NOW() END,CAST(:metrics AS jsonb)) "
                "ON CONFLICT (job_id,step_name,attempt) DO UPDATE SET status=EXCLUDED.status,"
                "finished_at=CASE WHEN EXCLUDED.status='completed' THEN NOW() ELSE report_job_steps.finished_at END,"
                "metrics=EXCLUDED.metrics,updated_at=NOW()"
            ), {"job": job_id, "name": name, "attempt": attempt, "status": status,
                "metrics": json.dumps(metrics)})

    def finish_success(self, job: dict, result: dict) -> bool:
        self._prepare_write()
        with self.db.begin():
            changed = self.db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET status='completed',progress_percent=100,"
                "result_payload=CAST(:result AS jsonb),validation_passed=:valid,finished_at=NOW(),"
                "worker_id=NULL,lease_until=NULL,updated_at=NOW() WHERE id=:id AND status='running' "
                "AND worker_id=:worker"
            ), {"result": json.dumps(result), "valid": bool(result.get("validation", {}).get("success")),
                "id": job["id"], "worker": job["worker_id"]}).rowcount == 1
            if changed:
                self._append_event(job["id"], "job.completed", "complete", 100, "Report completed", {})
                self._audit(job["report_id"], job["requested_by_subject_id"],
                            "report.activated", job["public_id"], {"job_id": str(job["public_id"])})
            return changed

    def finish_failure(self, job: dict, code: str, retryable: bool, message: str) -> str:
        self._prepare_write()
        with self.db.begin():
            current = _mapping(self.db.execute(sa.text(
                "SELECT attempt,max_attempts,report_id,status,worker_id FROM inspection_report.report_jobs "
                "WHERE id=:id FOR UPDATE"
            ), {"id": job["id"]}))
            if not current or current["status"] != "running" or current["worker_id"] != job["worker_id"]:
                return current["status"] if current else "lost"
            retry = retryable and current["attempt"] < current["max_attempts"]
            status = "retry_wait" if retry else "failed"
            self.db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET status=:status,error_code=:code,"
                "available_at=CASE WHEN :retry THEN NOW()+make_interval(secs=>power(2,attempt)::int) ELSE available_at END,"
                "finished_at=CASE WHEN :retry THEN NULL ELSE NOW() END,worker_id=NULL,lease_until=NULL,updated_at=NOW() WHERE id=:id"
            ), {"status": status, "code": code, "retry": retry, "id": job["id"]})
            if not retry:
                self.db.execute(sa.text(
                    "UPDATE inspection_report.reports SET status='failed',version=version+1,updated_at=NOW() WHERE id=:id"
                ), {"id": current["report_id"]})
            self._append_event(job["id"], "job.retry_wait" if retry else "job.failed", status, None,
                               message, {"code": code})
            if not retry:
                self._audit(current["report_id"], job["requested_by_subject_id"],
                            "report.failed", job["public_id"],
                            {"job_id": str(job["public_id"]), "code": code})
            return status

    def finish_cancelled(self, job: dict) -> None:
        self._prepare_write()
        with self.db.begin():
            changed = self.db.execute(sa.text(
                "UPDATE inspection_report.report_jobs SET status='cancelled',finished_at=NOW(),worker_id=NULL,"
                "lease_until=NULL,updated_at=NOW() WHERE id=:id AND status='running' AND worker_id=:worker"
            ), {"id": job["id"], "worker": job["worker_id"]}).rowcount == 1
            if not changed:
                return
            self.db.execute(sa.text(
                "UPDATE inspection_report.reports SET status='failed',version=version+1,updated_at=NOW() WHERE id=:id"
            ), {"id": job["report_id"]})
            self._append_event(job["id"], "job.cancelled", "cancelled", job["progress_percent"],
                               "Report job cancelled at a safe stage boundary", {})
            self._audit(job["report_id"], job["requested_by_subject_id"],
                        "report.job_cancelled", job["public_id"],
                        {"job_id": str(job["public_id"])})

    def persist_pipeline_result(self, job: dict, report_payload: dict, region_info: list,
                                evidence_refs: list[str], validation_passed: bool) -> int:
        evidence_ids = [UUID(str(ref).removeprefix("/api/assets/").replace("-", "")) for ref in evidence_refs]
        self._prepare_write()
        with self.db.begin():
            current = _mapping(self.db.execute(sa.text(
                "SELECT r.status FROM inspection_report.reports r "
                "JOIN inspection_report.report_jobs j ON j.report_id=r.id "
                "WHERE r.id=:id AND j.id=:job AND j.status='running' AND j.worker_id=:worker "
                "AND j.lease_until>NOW() FOR UPDATE OF r,j"
            ), {"id": job["report_id"], "job": job["id"], "worker": job["worker_id"]}))
            if not current:
                raise RuntimeError("Report job lease was lost before persistence")
            if current["status"] == "active":
                return int(job["report_id"])
            self.db.execute(sa.text(
                "INSERT INTO inspection_report.report_analysis "
                "(report_id,video_file_id,region_info,report_payload,validation_passed,validation_errors) "
                "VALUES (:report,:file,CAST(:regions AS jsonb),CAST(:payload AS jsonb),:valid,'[]'::jsonb) "
                "ON CONFLICT (report_id) DO NOTHING"
            ), {"report": job["report_id"], "file": job["input_file_id"],
                "regions": json.dumps(region_info), "payload": json.dumps(report_payload), "valid": validation_passed})
            self.db.execute(sa.text(
                "INSERT INTO inspection_report.report_assets (report_id,file_id,asset_kind,sort_order) "
                "VALUES (:report,:file,'input_video',0) ON CONFLICT DO NOTHING"
            ), {"report": job["report_id"], "file": job["input_file_id"]})
            for index, evidence_id in enumerate(evidence_ids):
                self.db.execute(sa.text(
                    "INSERT INTO inspection_report.report_assets (report_id,file_id,asset_kind,sort_order) "
                    "SELECT :report,id,'evidence_image',:sort FROM inspection_report.files "
                    "WHERE public_id=:file AND report_id=:report ON CONFLICT DO NOTHING"
                ), {"report": job["report_id"], "file": evidence_id, "sort": index})
            self.db.execute(sa.text(
                "UPDATE inspection_report.reports SET title=COALESCE(NULLIF(CAST(:title AS text),''),title),"
                "status='active',completed_at=NOW(),version=version+1,updated_at=NOW() WHERE id=:id"
            ), {"title": str(report_payload.get("title") or "")[:255], "id": job["report_id"]})
        return int(job["report_id"])
