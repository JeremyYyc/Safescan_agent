"""Add identity service action tokens, versions, and granular permissions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260908_0002"
down_revision = "20260907_0001"
branch_labels = None
depends_on = None


IDENTITY_PERMISSIONS = (
    "iam:self:read",
    "iam:self:update",
    "iam:self:password_change",
    "iam:self:sessions_manage",
    "iam:user:read",
    "iam:user:status_manage",
    "iam:staff:create",
    "iam:staff:read",
    "iam:staff:employment_manage",
    "iam:staff:role_manage",
    "iam:customer:read",
    "iam:customer_status:read",
    "rbac:read",
    "iam:service_client:manage",
    "iam:audit:read",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {item["name"] for item in inspector.get_columns("users", schema="identity_access")}
    if "version" not in user_columns:
        op.add_column("users", sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
                      schema="identity_access")
        op.create_check_constraint("ck_users_version_positive", "users", "version > 0",
                                   schema="identity_access")
    if "locale" not in user_columns:
        op.add_column("users", sa.Column("locale", sa.Text(), nullable=False,
                                         server_default="zh-CN"), schema="identity_access")
        op.create_check_constraint("ck_users_locale_length_valid", "users",
                                   "length(locale) BETWEEN 2 AND 20", schema="identity_access")
    client_columns = {item["name"] for item in inspector.get_columns("service_clients",
                                                                      schema="identity_access")}
    if "version" not in client_columns:
        op.add_column("service_clients",
                      sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
                      schema="identity_access")
        op.create_check_constraint("ck_service_clients_version_positive", "service_clients",
                                   "version > 0", schema="identity_access")
    if not inspector.has_table("account_action_tokens", schema="identity_access"):
        op.create_table(
            "account_action_tokens",
            sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column("public_id", UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("requested_ip_hash", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint("purpose IN ('email_verify','password_reset','staff_activate')",
                               name="ck_account_action_tokens_purpose_valid"),
            sa.CheckConstraint("expires_at > created_at",
                               name="ck_account_action_tokens_expiry_after_creation"),
            sa.ForeignKeyConstraint(["user_id"], ["identity_access.users.id"], ondelete="CASCADE",
                                    name="fk_account_action_tokens_user_id_users"),
            sa.UniqueConstraint("public_id", name="uq_account_action_tokens_public_id"),
            sa.UniqueConstraint("token_hash", name="uq_account_action_tokens_token_hash"),
            schema="identity_access",
        )
        op.create_index("ix_account_action_tokens_user_id", "account_action_tokens", ["user_id"],
                        schema="identity_access")
        op.create_index("uq_identity_action_one_active_purpose", "account_action_tokens",
                        ["user_id", "purpose"], unique=True, schema="identity_access",
                        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"))
        op.create_index("ix_identity_action_expiry", "account_action_tokens", ["expires_at", "id"],
                        schema="identity_access",
                        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"))

    for code in IDENTITY_PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity_access.permissions (code,description,risk_level) "
                "VALUES (:code,:description,:risk_level) ON CONFLICT (code) DO NOTHING"
            ),
            {
                "code": code,
                "description": code.replace(":", " ").replace("_", " "),
                "risk_level": "high" if code.endswith(("manage", "password_change")) else "normal",
            },
        )
    bind.execute(
        sa.text(
            "INSERT INTO identity_access.role_permissions (role_id,permission_id) "
            "SELECT r.id,p.id FROM identity_access.roles r CROSS JOIN identity_access.permissions p "
            "WHERE r.code='manager_admin' AND p.code = ANY(CAST(:codes AS text[])) "
            "ON CONFLICT (role_id,permission_id) DO NOTHING"
        ),
        {"codes": list(IDENTITY_PERMISSIONS)},
    )


def downgrade() -> None:
    raise RuntimeError(
        "Identity service migration has no data-preserving downgrade; restore a backup or recreate "
        "the development database at the prior Git revision."
    )
