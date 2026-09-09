"""Property leasing P0 aggregate, concurrency guards, and contract audit tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260909_0003"
down_revision = "20260908_0002"
branch_labels = ("property_leasing_p0",)
depends_on = None

SCHEMA = "property_leasing"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.add_column("buildings", sa.Column("timezone", sa.Text(), nullable=False,
                                          server_default="Australia/Sydney"), schema=SCHEMA)
    op.create_check_constraint("timezone_not_blank", "buildings", "length(trim(timezone)) > 0",
                               schema=SCHEMA)

    op.add_column("prospect_cases", sa.Column("property_id", sa.BigInteger(), nullable=False),
                  schema=SCHEMA)
    op.create_foreign_key("fk_prospect_cases_property", "prospect_cases", "properties",
                          ["property_id"], ["id"], source_schema=SCHEMA,
                          referent_schema=SCHEMA, ondelete="RESTRICT")
    op.create_index("ix_property_cases_party_property", "prospect_cases",
                    ["prospect_party_id", "property_id", "status"], schema=SCHEMA)
    op.alter_column("prospect_contact_threads", "assigned_consultant_staff_id",
                    existing_type=UUID(as_uuid=True), nullable=True, schema=SCHEMA)
    op.add_column("prospect_contact_threads",
                  sa.Column("public_id", UUID(as_uuid=True), nullable=False,
                            server_default=sa.text("gen_random_uuid()")), schema=SCHEMA)
    op.create_unique_constraint("uq_contact_threads_public_id", "prospect_contact_threads",
                                ["public_id"], schema=SCHEMA)

    op.add_column("tenancy_applications", sa.Column("desired_start_on", sa.Date(), nullable=False),
                  schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("term_months", sa.Integer(), nullable=False),
                  schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("occupants", sa.Integer(), nullable=False),
                  schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("note", sa.Text()), schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("closed_reason", sa.Text()), schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("closed_at", sa.DateTime(timezone=True)),
                  schema=SCHEMA)
    op.add_column("tenancy_applications", sa.Column("winning_lease_id", sa.BigInteger()),
                  schema=SCHEMA)
    op.drop_constraint("status_valid", "tenancy_applications", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "status_valid", "tenancy_applications",
        "status IN ('draft','submitted','reviewing','approved','rejected','withdrawn','ineligible','expired')",
        schema=SCHEMA,
    )
    op.create_check_constraint("application_values_valid", "tenancy_applications",
                               "term_months BETWEEN 1 AND 120 AND occupants BETWEEN 1 AND 50",
                               schema=SCHEMA)
    op.create_foreign_key("fk_applications_winning_lease", "tenancy_applications", "leases",
                          ["winning_lease_id"], ["id"], source_schema=SCHEMA,
                          referent_schema=SCHEMA, ondelete="SET NULL")
    op.create_index("ix_property_applicant_status_created", "tenancy_applications",
                    ["applicant_id", "status", "created_at", "id"], schema=SCHEMA)

    op.add_column("leases", sa.Column("application_id", sa.BigInteger(), nullable=False), schema=SCHEMA)
    op.add_column("leases", sa.Column("offer_expires_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("leases", sa.Column("cancelled_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("leases", sa.Column("cancel_reason", sa.Text()), schema=SCHEMA)
    op.create_foreign_key("fk_leases_application", "leases", "tenancy_applications",
                          ["application_id"], ["id"], source_schema=SCHEMA,
                          referent_schema=SCHEMA, ondelete="RESTRICT")
    op.create_unique_constraint("uq_leases_application_id", "leases", ["application_id"], schema=SCHEMA)
    op.drop_constraint("status_valid", "leases", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "status_valid", "leases",
        "status IN ('draft','pending_signature','executed','active','ended','terminated','cancelled','expired')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "lease_offer_expiry_required", "leases",
        "status NOT IN ('pending_signature') OR offer_expires_at IS NOT NULL", schema=SCHEMA,
    )
    op.execute(
        "ALTER TABLE property_leasing.leases ADD CONSTRAINT "
        "ex_property_active_date_overlap EXCLUDE USING gist "
        "(property_id WITH =, daterange(starts_on, ends_on, '[]') WITH &&) "
        "WHERE (status IN ('pending_signature','executed','active'))"
    )

    op.add_column("lease_tenants", sa.Column("version", sa.Integer(), nullable=False,
                                              server_default="1"), schema=SCHEMA)
    op.create_check_constraint("version_positive", "lease_tenants", "version > 0", schema=SCHEMA)
    op.create_unique_constraint("uq_lease_tenants_one_tenant", "lease_tenants", ["lease_id"],
                                schema=SCHEMA)

    op.create_table(
        "lease_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("lease_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("terms_payload", JSONB(), nullable=False),
        sa.Column("terms_digest", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="issued"),
        sa.Column("created_by_subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["lease_id"], [f"{SCHEMA}.leases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("lease_id", "version"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint("status IN ('issued','superseded')", name="status_valid"),
        schema=SCHEMA,
    )
    op.create_index("ix_property_lease_documents_current", "lease_documents",
                    ["lease_id", "version"], schema=SCHEMA)

    op.create_table(
        "lease_signature_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("lease_id", sa.BigInteger(), nullable=False),
        sa.Column("lease_document_id", sa.BigInteger(), nullable=False),
        sa.Column("signer_subject_id", UUID(as_uuid=True)),
        sa.Column("signer_staff_id", UUID(as_uuid=True)),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("terms_digest", sa.Text(), nullable=False),
        sa.Column("ip_hash", sa.Text()),
        sa.Column("user_agent_hash", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["lease_id"], [f"{SCHEMA}.leases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lease_document_id"], [f"{SCHEMA}.lease_documents.id"],
                                ondelete="RESTRICT"),
        sa.CheckConstraint(
            "(side='tenant' AND signer_subject_id IS NOT NULL AND signer_staff_id IS NULL) OR "
            "(side='company' AND signer_subject_id IS NULL AND signer_staff_id IS NOT NULL)",
            name="signer_matches_side",
        ),
        sa.UniqueConstraint("lease_id", "lease_document_id", "side", name="uq_signature_side"),
        schema=SCHEMA,
    )

    op.create_table(
        "customer_lease_slots",
        sa.Column("customer_subject_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lease_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["lease_id"], [f"{SCHEMA}.leases.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('pending_signature','executed','active')", name="status_valid"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("actor_subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", JSONB(), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_subject_id", "operation", "idempotency_key",
                            name="uq_idempotency_actor_operation_key"),
        sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        schema=SCHEMA,
    )
    op.create_index("ix_property_idempotency_expiry", "idempotency_records", ["expires_at", "id"],
                    schema=SCHEMA)

    op.create_table(
        "customer_event_versions",
        sa.Column("customer_subject_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("aggregate_version >= 0", name="aggregate_version_nonnegative"),
        schema=SCHEMA,
    )

    op.drop_table("lease_access_grants", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "lease_access_grants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("lease_id", sa.BigInteger(), nullable=False),
        sa.Column("party_id", sa.BigInteger(), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("access_mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("source_event_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["lease_id"], [f"{SCHEMA}.leases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["party_id"], [f"{SCHEMA}.parties.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("lease_id", "subject_id"),
        sa.CheckConstraint("access_mode IN ('full','read_only')", name="access_mode_valid"),
        sa.CheckConstraint("status IN ('active','expired','revoked')", name="status_valid"),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from",
                           name="effective_period"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        schema=SCHEMA,
    )
    op.create_index("ix_property_lease_grants_subject", "lease_access_grants",
                    ["subject_id", "status", "effective_from", "effective_until", "lease_id"],
                    schema=SCHEMA)

    op.drop_table("customer_event_versions", schema=SCHEMA)
    op.drop_index("ix_property_idempotency_expiry", table_name="idempotency_records", schema=SCHEMA)
    op.drop_table("idempotency_records", schema=SCHEMA)
    op.drop_table("customer_lease_slots", schema=SCHEMA)
    op.drop_table("lease_signature_events", schema=SCHEMA)
    op.drop_index("ix_property_lease_documents_current", table_name="lease_documents", schema=SCHEMA)
    op.drop_table("lease_documents", schema=SCHEMA)

    op.drop_constraint("uq_lease_tenants_one_tenant", "lease_tenants", schema=SCHEMA,
                       type_="unique")
    op.drop_constraint("version_positive", "lease_tenants", schema=SCHEMA, type_="check")
    op.drop_column("lease_tenants", "version", schema=SCHEMA)

    op.execute("ALTER TABLE property_leasing.leases DROP CONSTRAINT ex_property_active_date_overlap")
    op.drop_constraint("lease_offer_expiry_required", "leases", schema=SCHEMA, type_="check")
    op.drop_constraint("status_valid", "leases", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "status_valid", "leases",
        "status IN ('draft','pending_signature','executed','active','ended','terminated','cancelled')",
        schema=SCHEMA,
    )
    op.drop_constraint("uq_leases_application_id", "leases", schema=SCHEMA, type_="unique")
    op.drop_constraint("fk_leases_application", "leases", schema=SCHEMA, type_="foreignkey")
    op.drop_column("leases", "cancel_reason", schema=SCHEMA)
    op.drop_column("leases", "cancelled_at", schema=SCHEMA)
    op.drop_column("leases", "offer_expires_at", schema=SCHEMA)
    op.drop_column("leases", "application_id", schema=SCHEMA)

    op.drop_index("ix_property_applicant_status_created", table_name="tenancy_applications",
                  schema=SCHEMA)
    op.drop_constraint("fk_applications_winning_lease", "tenancy_applications", schema=SCHEMA,
                       type_="foreignkey")
    op.drop_constraint("application_values_valid", "tenancy_applications", schema=SCHEMA,
                       type_="check")
    op.drop_constraint("status_valid", "tenancy_applications", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "status_valid", "tenancy_applications",
        "status IN ('draft','submitted','reviewing','approved','rejected','withdrawn')", schema=SCHEMA,
    )
    for column in ("winning_lease_id", "closed_at", "closed_reason", "note", "occupants",
                   "term_months", "desired_start_on"):
        op.drop_column("tenancy_applications", column, schema=SCHEMA)

    op.drop_constraint("uq_contact_threads_public_id", "prospect_contact_threads", schema=SCHEMA,
                       type_="unique")
    op.drop_column("prospect_contact_threads", "public_id", schema=SCHEMA)
    op.alter_column("prospect_contact_threads", "assigned_consultant_staff_id",
                    existing_type=UUID(as_uuid=True), nullable=False, schema=SCHEMA)
    op.drop_index("ix_property_cases_party_property", table_name="prospect_cases", schema=SCHEMA)
    op.drop_constraint("fk_prospect_cases_property", "prospect_cases", schema=SCHEMA,
                       type_="foreignkey")
    op.drop_column("prospect_cases", "property_id", schema=SCHEMA)
    op.drop_constraint("timezone_not_blank", "buildings", schema=SCHEMA, type_="check")
    op.drop_column("buildings", "timezone", schema=SCHEMA)
