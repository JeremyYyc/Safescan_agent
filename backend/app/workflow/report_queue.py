"""PostgreSQL-backed report queue and a small, restart-safe worker.

The queue is the source of truth for delivery and ownership. LangGraph stores
the finer grained state under the same job id, so a worker can resume a graph
after a process crash without replaying completed nodes.
"""
import logging
import threading
import time
from uuid import uuid4

from app import db, storage
from app.persistence.database import get_connection
from app.settings import get_settings

logger = logging.getLogger(__name__)


def enqueue_report_job(*, user_id, chat_id, video_asset_id, attributes):
    """Create exactly one active job per chat, returning an existing one."""
    with get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT job_id, status FROM report_jobs WHERE chat_id=%s "
            "AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
            (chat_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return existing['job_id'], False
        job_id = uuid4().hex
        cursor.execute(
            "INSERT INTO report_jobs (job_id,user_id,chat_id,video_asset_id,attributes,status) "
            "VALUES (%s,%s,%s,%s,CAST(%s AS JSONB),'queued')",
            (job_id, user_id, chat_id, video_asset_id, __import__('json').dumps(attributes or {})),
        )
        _append_event(cursor, job_id, {'type': 'queued', 'job_id': job_id})
        return job_id, True


def _append_event(cursor, job_id, event):
    cursor.execute(
        "INSERT INTO report_job_events (job_id,event) VALUES (%s,CAST(%s AS JSONB))",
        (job_id, __import__('json').dumps(event, ensure_ascii=False)),
    )


def get_report_job(job_id, user_id=None):
    with get_connection() as conn, conn.cursor(True) as cursor:
        query = "SELECT job_id,user_id,chat_id,video_asset_id,attributes,status,attempt,error,result,created_at,updated_at FROM report_jobs WHERE job_id=%s"
        params = [job_id]
        if user_id is not None:
            query += " AND user_id=%s"; params.append(user_id)
        cursor.execute(query, tuple(params))
        return cursor.fetchone()


def get_report_job_events(job_id, after_sequence=0):
    with get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(
            "SELECT sequence,event FROM report_job_events WHERE job_id=%s AND sequence>%s ORDER BY sequence",
            (job_id, after_sequence),
        )
        return cursor.fetchall()


def claim_report_job(worker_id):
    """Atomically lease one item; SKIP LOCKED permits multiple workers."""
    lease = get_settings().REPORT_JOB_LEASE_SECONDS
    with get_connection() as conn, conn.cursor(True) as cursor:
        cursor.execute(
            "WITH candidate AS (SELECT job_id FROM report_jobs WHERE status='queued' "
            "OR (status='running' AND lease_expires_at < CURRENT_TIMESTAMP) "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) "
            "UPDATE report_jobs j SET status='running', locked_by=%s, "
            "lease_expires_at=CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'), "
            "attempt=j.attempt+1, updated_at=CURRENT_TIMESTAMP FROM candidate "
            "WHERE j.job_id=candidate.job_id RETURNING j.job_id,j.user_id,j.chat_id,j.video_asset_id,j.attributes,j.attempt",
            (worker_id, lease),
        )
        job = cursor.fetchone()
        if job:
            _append_event(cursor, job['job_id'], {'type': 'running', 'job_id': job['job_id'], 'attempt': job['attempt']})
        return job


def append_job_trace(job_id, entry):
    with get_connection() as conn, conn.cursor() as cursor:
        _append_event(cursor, job_id, {'type': 'trace', 'entry': entry})


def finish_report_job(job_id, result):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE report_jobs SET status='succeeded', result=CAST(%s AS JSONB), error=NULL, lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE job_id=%s", (__import__('json').dumps(result, ensure_ascii=False), job_id))
        _append_event(cursor, job_id, {'type': 'complete', 'result': result})


def fail_report_job(job_id, message, code='report_generation_failed'):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE report_jobs SET status='failed', error=%s, lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE job_id=%s", (message[:1000], job_id))
        _append_event(cursor, job_id, {'type': 'error', 'code': code, 'message': message})


class ReportJobWorker:
    def __init__(self, worker_id=None):
        self.worker_id = worker_id or f"report-{uuid4().hex[:12]}"

    def run_once(self):
        job = claim_report_job(self.worker_id)
        if not job:
            return False
        from app.workflow.graph import WorkflowCancelled
        from app.workflow.orchestrator import WorkflowOrchestrator, result_payload
        try:
            state = WorkflowOrchestrator().execute_workflow(
                job['video_asset_id'], job['attributes'] or {}, user_id=job['user_id'], chat_id=job['chat_id'],
                run_id=job['job_id'], trace_cb=lambda entry: append_job_trace(job['job_id'], entry),
                checkpoint_thread_id=job['job_id'], resume=job['attempt'] > 1,
            )
            result = result_payload(state)
            if state.get('warning'):
                fail_report_job(job['job_id'], state['warning'], 'workflow_incomplete')
            elif not state.get('report_id'):
                fail_report_job(job['job_id'], 'Report persistence did not complete. Please retry.')
            else:
                finish_report_job(job['job_id'], result)
        except WorkflowCancelled:
            fail_report_job(job['job_id'], '分析流程已取消', 'cancelled')
        except Exception:
            logger.exception('Report job failed job_id=%s', job['job_id'])
            fail_report_job(job['job_id'], '报告生成失败，分析流程未成功完成')
        return True

    def serve_forever(self):
        while True:
            try:
                worked = self.run_once()
            except Exception:
                # A worker may start while Alembic is still applying migrations.
                # Keep it alive so it can claim persisted jobs once the database is ready.
                logger.exception('Report queue poll failed')
                worked = False
            if not worked:
                time.sleep(get_settings().REPORT_JOB_POLL_SECONDS)


def start_embedded_worker():
    """Wake a worker for local/single-container deployments; leasing makes it safe."""
    threading.Thread(target=ReportJobWorker().run_once, daemon=True).start()
