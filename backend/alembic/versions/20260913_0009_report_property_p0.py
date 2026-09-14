"""Bind formal inspection reports to properties and durable jobs.

Revision ID: 20260913_0009
Revises: 20260910_0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260913_0009"
down_revision = "20260910_0007"
branch_labels = ("inspection_report_p0",)
depends_on = None

SCHEMA = "inspection_report"


def upgrade() -> None:
    # Existing rows are retained as compatibility records. Only records explicitly
    # promoted/created as formal reports are subject to the new ownership contract.
    op.add_column("reports", sa.Column("property_id", UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("reports", sa.Column("source_lease_id", UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("reports", sa.Column("created_by_account_type", sa.Text()), schema=SCHEMA)
    op.add_column("reports", sa.Column("legacy_context_id", sa.BigInteger()), schema=SCHEMA)
    op.add_column(
        "reports",
        sa.Column("is_formal", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.add_column(
        "reports",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.drop_constraint(op.f("ck_reports_status_valid"), "reports", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "status_valid",
        "reports",
        "status IN ('draft','processing','active','failed','deleted')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "formal_ownership",
        "reports",
        "NOT is_formal OR (property_id IS NOT NULL AND created_by_account_type IN ('staff','customer'))",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "customer_lease_required",
        "reports",
        "NOT is_formal OR created_by_account_type <> 'customer' OR source_lease_id IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint("version_positive", "reports", "version > 0", schema=SCHEMA)
    op.create_index("ix_reports_property_recent", "reports", ["property_id", "status", "created_at", "id"], schema=SCHEMA)
    op.create_index("ix_reports_source_lease", "reports", ["source_lease_id", "status", "id"], schema=SCHEMA)

    op.add_column("files", sa.Column("report_id", sa.BigInteger()), schema=SCHEMA)
    op.add_column("files", sa.Column("idempotency_key", UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("files", sa.Column("request_digest", sa.Text()), schema=SCHEMA)
    op.create_foreign_key(
        "fk_files_report_id_reports", "files", "reports", ["report_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="RESTRICT",
    )
    op.create_index("ix_files_report_id", "files", ["report_id"], schema=SCHEMA)
    op.create_index(
        "uq_files_actor_idempotency",
        "files",
        ["created_by_subject_id", "idempotency_key"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("report_jobs", sa.Column("request_digest", sa.Text()), schema=SCHEMA)
    op.add_column("report_jobs", sa.Column("cancel_reason", sa.Text()), schema=SCHEMA)
    op.add_column("report_jobs", sa.Column("next_event_sequence", sa.BigInteger(), nullable=False, server_default="1"), schema=SCHEMA)
    op.create_check_constraint("event_sequence_positive", "report_jobs", "next_event_sequence > 0", schema=SCHEMA)
    op.create_check_constraint(
        "formal_report_required",
        "report_jobs",
        "job_type NOT IN ('video_analysis','pdf_render') OR report_id IS NOT NULL OR source_service = 'legacy-backend'",
        schema=SCHEMA,
    )
    op.drop_constraint(op.f("uq_report_jobs_report_id"), "report_jobs", schema=SCHEMA, type_="unique")
    op.create_index(
        "uq_report_jobs_one_active_report",
        "report_jobs",
        ["report_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("report_id IS NOT NULL AND status IN ('queued','retry_wait','running')"),
    )

    op.create_table(
        "report_idempotency_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("actor_subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("actor_subject_id", "operation", "idempotency_key", name="uq_report_idempotency_actor_operation_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "report_audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("details_redacted", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["report_id"], [f"{SCHEMA}.reports.id"], ondelete="CASCADE", name="fk_report_audit_events_report_id_reports"),
        schema=SCHEMA,
    )
    op.create_index("ix_report_audit_events_report_id", "report_audit_events", ["report_id", "created_at", "id"], schema=SCHEMA)

    op.execute(
        """
        CREATE FUNCTION inspection_report.prevent_report_ownership_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.property_id IS DISTINCT FROM NEW.property_id
             OR OLD.source_lease_id IS DISTINCT FROM NEW.source_lease_id
             OR OLD.created_by_subject_id IS DISTINCT FROM NEW.created_by_subject_id
             OR OLD.created_by_account_type IS DISTINCT FROM NEW.created_by_account_type THEN
            RAISE EXCEPTION 'formal report ownership is immutable';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER reports_ownership_immutable
        BEFORE UPDATE OF property_id, source_lease_id, created_by_subject_id, created_by_account_type
        ON inspection_report.reports
        FOR EACH ROW WHEN (OLD.is_formal)
        EXECUTE FUNCTION inspection_report.prevent_report_ownership_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER reports_ownership_immutable ON inspection_report.reports")
    op.execute("DROP FUNCTION inspection_report.prevent_report_ownership_change()")
    op.drop_index("ix_report_audit_events_report_id", table_name="report_audit_events", schema=SCHEMA)
    op.drop_table("report_audit_events", schema=SCHEMA)
    op.drop_table("report_idempotency_records", schema=SCHEMA)
    op.drop_index("uq_report_jobs_one_active_report", table_name="report_jobs", schema=SCHEMA)
    op.create_unique_constraint("uq_report_jobs_report_id", "report_jobs", ["report_id"], schema=SCHEMA)
    op.drop_constraint(op.f("ck_report_jobs_formal_report_required"), "report_jobs", schema=SCHEMA, type_="check")
    op.drop_constraint(op.f("ck_report_jobs_event_sequence_positive"), "report_jobs", schema=SCHEMA, type_="check")
    for column in ("next_event_sequence", "cancel_reason", "request_digest"):
        op.drop_column("report_jobs", column, schema=SCHEMA)
    op.drop_index("uq_files_actor_idempotency", table_name="files", schema=SCHEMA)
    op.drop_index("ix_files_report_id", table_name="files", schema=SCHEMA)
    op.drop_constraint("fk_files_report_id_reports", "files", schema=SCHEMA, type_="foreignkey")
    for column in ("request_digest", "idempotency_key", "report_id"):
        op.drop_column("files", column, schema=SCHEMA)
    op.drop_index("ix_reports_source_lease", table_name="reports", schema=SCHEMA)
    op.drop_index("ix_reports_property_recent", table_name="reports", schema=SCHEMA)
    op.drop_constraint(op.f("ck_reports_version_positive"), "reports", schema=SCHEMA, type_="check")
    op.drop_constraint(op.f("ck_reports_customer_lease_required"), "reports", schema=SCHEMA, type_="check")
    op.drop_constraint(op.f("ck_reports_formal_ownership"), "reports", schema=SCHEMA, type_="check")
    op.drop_constraint(op.f("ck_reports_status_valid"), "reports", schema=SCHEMA, type_="check")
    op.create_check_constraint("status_valid", "reports", "status IN ('active','deleted')", schema=SCHEMA)
    for column in ("version", "is_formal", "legacy_context_id", "created_by_account_type", "source_lease_id", "property_id"):
        op.drop_column("reports", column, schema=SCHEMA)
