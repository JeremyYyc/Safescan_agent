"""Add ordered customer tenancy projections and report generation permissions."""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260908_0003"
down_revision = "20260908_0002"
branch_labels = None
depends_on = None


P0_ROLE_PERMISSIONS = {
    "leasing_consultant": {
        "property:read_market", "prospect:manage", "application:manage", "lease:prepare",
        "lease:execute", "agent:staff:use",
    },
    "property_manager": {
        "building:read_assigned", "property:manage_assigned", "lease:manage_active_assigned",
        "maintenance:assign_assigned", "maintenance:update_assigned", "report:read_assigned",
        "report:generate_assigned", "agent:staff:use",
    },
    "maintainer": {
        "work_order:read_assigned", "work_order:update_assigned", "work_order:evidence_write",
        "property:read_work_context", "report:read_work_context", "agent:staff:use",
    },
}
P0_ROLE_PERMISSIONS["manager_admin"] = {
    *(permission for permissions in P0_ROLE_PERMISSIONS.values() for permission in permissions),
    "building:read_all", "property:read_all", "prospect:manage_all", "application:manage_all",
    "lease:manage_all", "maintenance:manage_all", "report:read_all", "report:generate_all",
    "iam:user:read", "iam:user:status_manage", "iam:staff:create", "iam:staff:read",
    "iam:staff:employment_manage", "iam:staff:role_manage", "iam:audit:read", "rbac:read",
    "rbac:manage", "scope:manage",
}

PREVIOUS_ROLE_PERMISSIONS = {
    "leasing_consultant": {
        "property:read_market", "property:manage_vacancy", "prospect:manage", "viewing:manage",
        "application:manage", "lease:prepare", "lease:execute",
    },
    "property_manager": {
        "building:read_assigned", "property:manage_assigned", "lease:manage_active_assigned",
        "maintenance:create_assigned", "maintenance:assign_assigned", "inspection:manage_assigned",
        "report:manage_assigned",
    },
    "maintainer": {
        "work_order:read_assigned", "work_order:update_assigned", "work_order:evidence_write",
        "property:read_work_context", "report:read_work_context",
    },
}
PREVIOUS_ROLE_PERMISSIONS["manager_admin"] = {
    *(permission for permissions in PREVIOUS_ROLE_PERMISSIONS.values() for permission in permissions),
    "iam:manage", "rbac:manage", "scope:manage", "iam:self:read", "iam:self:update",
    "iam:self:password_change", "iam:self:sessions_manage", "iam:user:read",
    "iam:user:status_manage", "iam:staff:create", "iam:staff:read",
    "iam:staff:employment_manage", "iam:staff:role_manage", "iam:customer:read",
    "iam:customer_status:read", "rbac:read", "iam:service_client:manage", "iam:audit:read",
}

P0_SERVICE_CLIENTS = {
    "property-leasing": {
        "identity:customer_status_write", "identity:subject_read",
        "identity:subject_deletion_ack", "identity:subject_deletion_read",
        "identity:subject_tombstone_check",
    },
    "maintenance": {
        "identity:subject_read", "identity:subject_deletion_ack",
        "identity:subject_deletion_read", "identity:subject_tombstone_check",
    },
    "inspection-report": {
        "identity:subject_read", "identity:subject_deletion_ack",
        "identity:subject_deletion_read", "identity:subject_tombstone_check",
    },
    "staff-portal": {"identity:token_exchange", "identity:token_introspect", "identity:subject_read"},
    "tenant-portal": {"identity:token_exchange", "identity:token_introspect", "identity:subject_read"},
}


def _replace_role_permissions(bind, matrix: dict[str, set[str]]) -> None:
    role_codes = sorted(matrix)
    bind.execute(sa.text(
        "DELETE FROM identity_access.role_permissions rp USING identity_access.roles r "
        "WHERE rp.role_id=r.id AND r.code = ANY(CAST(:role_codes AS text[]))"
    ), {"role_codes": role_codes})
    for role_code, permission_codes in matrix.items():
        bind.execute(sa.text(
            "INSERT INTO identity_access.role_permissions (role_id,permission_id) "
            "SELECT r.id,p.id FROM identity_access.roles r JOIN identity_access.permissions p "
            "ON p.code = ANY(CAST(:permission_codes AS text[])) WHERE r.code=:role_code"
        ), {"role_code": role_code, "permission_codes": sorted(permission_codes)})


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    profile_columns = {
        item["name"] for item in inspector.get_columns("customer_profiles", schema="identity_access")
    }
    if "tenancy_version" not in profile_columns:
        op.add_column(
            "customer_profiles",
            sa.Column("tenancy_version", sa.Integer(), nullable=False, server_default="0"),
            schema="identity_access",
        )
        op.create_check_constraint(
            op.f("ck_customer_profiles_tenancy_version_nonnegative"),
            "customer_profiles",
            "tenancy_version >= 0",
            schema="identity_access",
        )

    event_columns = {
        item["name"] for item in inspector.get_columns("customer_status_events", schema="identity_access")
    }
    if "source_aggregate_version" not in event_columns:
        op.add_column(
            "customer_status_events",
            sa.Column("source_aggregate_version", sa.Integer(), nullable=True),
            schema="identity_access",
        )
        op.execute(
            "UPDATE identity_access.customer_status_events "
            "SET source_aggregate_version=id WHERE source_aggregate_version IS NULL"
        )
        op.alter_column(
            "customer_status_events", "source_aggregate_version", nullable=False,
            schema="identity_access",
        )
        op.create_check_constraint(
            op.f("ck_customer_status_events_source_aggregate_version_positive"),
            "customer_status_events",
            "source_aggregate_version > 0",
            schema="identity_access",
        )
    op.execute(
        "UPDATE identity_access.customer_profiles AS cp SET tenancy_version=events.max_version "
        "FROM (SELECT customer_id,MAX(source_aggregate_version) AS max_version "
        "FROM identity_access.customer_status_events GROUP BY customer_id) AS events "
        "WHERE cp.id=events.customer_id AND cp.tenancy_version < events.max_version"
    )

    existing_indexes = {
        item["name"] for item in inspector.get_indexes("customer_status_events", schema="identity_access")
    }
    if "uq_identity_customer_status_aggregate_version" not in existing_indexes:
        op.create_index(
            "uq_identity_customer_status_aggregate_version",
            "customer_status_events",
            ["customer_id", "source_aggregate_version"],
            unique=True,
            schema="identity_access",
        )

    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check", schema="identity_access")
    op.create_check_constraint(
        op.f("ck_users_status_valid"), "users",
        "status IN ('pending','active','suspended','deletion_pending','deleted')",
        schema="identity_access",
    )
    if not inspector.has_table("subject_deletion_requests", schema="identity_access"):
        op.create_table(
            "subject_deletion_requests",
            sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column("public_id", UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", sa.BigInteger()),
            sa.Column("subject_id", UUID(as_uuid=True)),
            sa.Column("status", sa.Text(), nullable=False, server_default="checking"),
            sa.Column("reason", sa.Text()),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("blocker_summary", JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("required_services", JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["user_id"], ["identity_access.users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("status IN ('checking','blocked','processing','completed','failed')",
                               name="ck_subject_deletion_requests_status_valid"),
            sa.UniqueConstraint("public_id", name="uq_subject_deletion_requests_public_id"),
            schema="identity_access",
        )
        op.create_index(
            "uq_identity_deletion_active_subject", "subject_deletion_requests", ["subject_id"],
            unique=True, schema="identity_access",
            postgresql_where=sa.text("subject_id IS NOT NULL AND status <> 'completed'"),
        )
        op.create_index(
            "uq_identity_deletion_subject_idempotency", "subject_deletion_requests",
            ["subject_id", "idempotency_key"], unique=True, schema="identity_access",
            postgresql_where=sa.text("subject_id IS NOT NULL"),
        )
    if not inspector.has_table("subject_deletion_acknowledgements", schema="identity_access"):
        op.create_table(
            "subject_deletion_acknowledgements",
            sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column("request_id", sa.BigInteger(), nullable=False),
            sa.Column("service", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("details_redacted", JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["request_id"], ["identity_access.subject_deletion_requests.id"],
                                    ondelete="CASCADE"),
            sa.CheckConstraint("status IN ('completed','failed')",
                               name="ck_subject_deletion_acknowledgements_status_valid"),
            sa.CheckConstraint("attempt > 0",
                               name="ck_subject_deletion_acknowledgements_attempt_positive"),
            sa.UniqueConstraint("request_id", "service", name="uq_deletion_ack_request_service"),
            schema="identity_access",
        )
    if not inspector.has_table("subject_deletion_tombstones", schema="identity_access"):
        op.create_table(
            "subject_deletion_tombstones",
            sa.Column("deletion_request_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("subject_fingerprint", sa.LargeBinary(), nullable=False, unique=True),
            sa.Column("fingerprint_version", sa.SmallInteger(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="completed"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("fingerprint_version > 0",
                               name="ck_subject_deletion_tombstones_fingerprint_version_positive"),
            sa.CheckConstraint("status = 'completed'",
                               name="ck_subject_deletion_tombstones_status_completed"),
            schema="identity_access",
        )

    all_codes = sorted({code for codes in P0_ROLE_PERMISSIONS.values() for code in codes})
    for code in all_codes:
        bind.execute(
            sa.text(
                "INSERT INTO identity_access.permissions (code,description,risk_level) "
                "VALUES (:code,:description,:risk_level) ON CONFLICT (code) DO NOTHING"
            ),
            {
                "code": code,
                "description": code.replace(":", " ").replace("_", " "),
                "risk_level": "high" if code == "report:generate_all" else "normal",
            },
        )
    _replace_role_permissions(bind, P0_ROLE_PERMISSIONS)
    bind.execute(sa.text(
        "UPDATE identity_access.roles SET version=version+1, updated_at=CURRENT_TIMESTAMP "
        "WHERE code = ANY(CAST(:role_codes AS text[]))"
    ), {"role_codes": sorted(P0_ROLE_PERMISSIONS)})
    for client_code, scopes in P0_SERVICE_CLIENTS.items():
        bind.execute(sa.text(
            "INSERT INTO identity_access.service_clients "
            "(client_code,credential_ref,allowed_audiences,allowed_scopes,status,key_id,version) "
            "VALUES (:client_code,:credential_ref,CAST(:audiences AS jsonb),CAST(:scopes AS jsonb),"
            "'active',NULL,1) ON CONFLICT (client_code) DO NOTHING"
        ), {
            "client_code": client_code,
            "credential_ref": f"seed://identity-p0/{client_code}",
            "audiences": json.dumps(["safescan-identity-internal"]),
            "scopes": json.dumps(sorted(scopes)),
        })


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM identity_access.service_clients "
        "WHERE client_code = ANY(CAST(:client_codes AS text[])) AND credential_ref LIKE 'seed://identity-p0/%'"
    ), {"client_codes": sorted(P0_SERVICE_CLIENTS)})
    _replace_role_permissions(bind, PREVIOUS_ROLE_PERMISSIONS)
    bind.execute(sa.text(
        "UPDATE identity_access.roles SET version=GREATEST(version-1,1), updated_at=CURRENT_TIMESTAMP "
        "WHERE code = ANY(CAST(:role_codes AS text[]))"
    ), {"role_codes": sorted(P0_ROLE_PERMISSIONS)})
    op.drop_table("subject_deletion_tombstones", schema="identity_access")
    op.drop_table("subject_deletion_acknowledgements", schema="identity_access")
    op.drop_index("uq_identity_deletion_subject_idempotency",
                  table_name="subject_deletion_requests", schema="identity_access")
    op.drop_index("uq_identity_deletion_active_subject",
                  table_name="subject_deletion_requests", schema="identity_access")
    op.drop_table("subject_deletion_requests", schema="identity_access")
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check", schema="identity_access")
    op.create_check_constraint(
        op.f("ck_users_status_valid"), "users", "status IN ('pending','active','suspended','deleted')",
        schema="identity_access",
    )
    op.drop_index("uq_identity_customer_status_aggregate_version",
                  table_name="customer_status_events", schema="identity_access")
    op.drop_constraint(op.f("ck_customer_status_events_source_aggregate_version_positive"),
                       "customer_status_events", type_="check", schema="identity_access")
    op.drop_column("customer_status_events", "source_aggregate_version", schema="identity_access")
    op.drop_constraint(op.f("ck_customer_profiles_tenancy_version_nonnegative"),
                       "customer_profiles", type_="check", schema="identity_access")
    op.drop_column("customer_profiles", "tenancy_version", schema="identity_access")
