"""Single-company microservice schema baseline.

This project has no production data to preserve. Existing development databases
must be recreated rather than upgraded through a compatibility or dual-write
path.
"""

from alembic import op
import sqlalchemy as sa

from app.persistence.target_schema import SERVICE_SCHEMAS, metadata


revision = "20260907_0001"
down_revision = None
branch_labels = None
depends_on = None


ROLE_PERMISSIONS = {
    "leasing_consultant": {
        "property:read_market",
        "property:manage_vacancy",
        "prospect:manage",
        "viewing:manage",
        "application:manage",
        "lease:prepare",
        "lease:execute",
    },
    "property_manager": {
        "building:read_assigned",
        "property:manage_assigned",
        "lease:manage_active_assigned",
        "maintenance:create_assigned",
        "maintenance:assign_assigned",
        "inspection:manage_assigned",
        "report:manage_assigned",
    },
    "maintainer": {
        "work_order:read_assigned",
        "work_order:update_assigned",
        "work_order:evidence_write",
        "property:read_work_context",
        "report:read_work_context",
    },
}
ROLE_PERMISSIONS["manager_admin"] = {
    "iam:manage",
    "rbac:manage",
    "scope:manage",
    *(permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions),
}

AGENT_DEFINITIONS = (
    ("intent-router", "local"),
    ("record-query-agent", "local"),
    ("knowledge-qa-agent", "local"),
    ("operation-agent", "local"),
)


def _seed_rbac(bind) -> None:
    role_rows = [
        {"code": "leasing_consultant", "name": "Leasing Consultant"},
        {"code": "property_manager", "name": "Property Manager"},
        {"code": "maintainer", "name": "Maintainer"},
        {"code": "manager_admin", "name": "Manager Admin"},
    ]
    permission_codes = sorted({code for values in ROLE_PERMISSIONS.values() for code in values})
    bind.execute(
        sa.text(
            "INSERT INTO identity_access.roles (code,name,status,version) "
            "VALUES (:code,:name,'active',1)"
        ),
        role_rows,
    )
    bind.execute(
        sa.text(
            "INSERT INTO identity_access.permissions (code,description,risk_level) "
            "VALUES (:code,:description,:risk_level)"
        ),
        [
            {
                "code": code,
                "description": code.replace(":", " ").replace("_", " "),
                "risk_level": "high" if code in {"iam:manage", "rbac:manage", "scope:manage", "lease:execute"} else "normal",
            }
            for code in permission_codes
        ],
    )
    for role_code, permission_set in ROLE_PERMISSIONS.items():
        bind.execute(
            sa.text(
                "INSERT INTO identity_access.role_permissions (role_id,permission_id) "
                "SELECT r.id,p.id FROM identity_access.roles r "
                "JOIN identity_access.permissions p "
                "ON p.code = ANY(CAST(:permission_codes AS text[])) "
                "WHERE r.code=:role_code"
            ),
            {"role_code": role_code, "permission_codes": sorted(permission_set)},
        )


def _seed_agent_definitions(bind) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO staff_agent.agent_definitions "
            "(code,version,transport,capabilities,enabled) "
            "VALUES (:code,1,:transport,CAST(:capabilities AS jsonb),true)"
        ),
        [
            {
                "code": code,
                "transport": transport,
                "capabilities": "{}",
            }
            for code, transport in AGENT_DEFINITIONS
        ],
    )


def upgrade() -> None:
    bind = op.get_bind()
    for schema in SERVICE_SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    metadata.create_all(bind=bind, checkfirst=False)

    op.execute(
        """
        CREATE FUNCTION identity_access.enforce_profile_account_type()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected_type text;
        BEGIN
          expected_type := CASE TG_TABLE_NAME
            WHEN 'staff' THEN 'staff'
            WHEN 'customer_profiles' THEN 'customer'
          END;
          IF NOT EXISTS (
            SELECT 1 FROM identity_access.users
            WHERE id = NEW.user_id AND account_type = expected_type
          ) THEN
            RAISE EXCEPTION 'profile does not match users.account_type';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_account_type_guard
        BEFORE INSERT OR UPDATE OF user_id ON identity_access.staff
        FOR EACH ROW EXECUTE FUNCTION identity_access.enforce_profile_account_type()
        """
    )
    op.execute(
        """
        CREATE TRIGGER customer_account_type_guard
        BEFORE INSERT OR UPDATE OF user_id ON identity_access.customer_profiles
        FOR EACH ROW EXECUTE FUNCTION identity_access.enforce_profile_account_type()
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_access.prevent_account_identity_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.email IS DISTINCT FROM NEW.email THEN
            RAISE EXCEPTION 'email is the immutable account identity';
          END IF;
          IF OLD.account_type IS DISTINCT FROM NEW.account_type THEN
            RAISE EXCEPTION 'account_type is immutable after account creation';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_account_identity_immutable
        BEFORE UPDATE OF email, account_type ON identity_access.users
        FOR EACH ROW EXECUTE FUNCTION identity_access.prevent_account_identity_change()
        """
    )
    _seed_rbac(bind)
    _seed_agent_definitions(bind)


def downgrade() -> None:
    raise RuntimeError(
        "This direct-rebuild baseline has no data-preserving downgrade; recreate the development database at the prior Git revision."
    )
