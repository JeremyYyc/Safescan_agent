"""Reconcile persisted staff permissions with the frozen P0 role matrix.

Revision 20260908_0003 was changed while some long-lived development databases
had already recorded it as applied.  Alembic therefore could not replay the
new permission replacement for those databases.  This forward-only repair
normalizes both fresh and existing databases without deleting user data.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0006"
down_revision = "20260910_0005"
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


def upgrade() -> None:
    bind = op.get_bind()
    role_codes = sorted(P0_ROLE_PERMISSIONS)
    permission_codes = sorted({
        code for permissions in P0_ROLE_PERMISSIONS.values() for code in permissions
    })

    role_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM identity_access.roles "
            "WHERE code = ANY(CAST(:role_codes AS text[]))"
        ),
        {"role_codes": role_codes},
    ).scalar_one()
    if role_count != len(role_codes):
        raise RuntimeError("Cannot reconcile P0 permissions: one or more seeded roles are missing")

    for code in permission_codes:
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

    bind.execute(
        sa.text(
            "DELETE FROM identity_access.role_permissions rp USING identity_access.roles r "
            "WHERE rp.role_id=r.id AND r.code = ANY(CAST(:role_codes AS text[]))"
        ),
        {"role_codes": role_codes},
    )
    for role_code, codes in P0_ROLE_PERMISSIONS.items():
        bind.execute(
            sa.text(
                "INSERT INTO identity_access.role_permissions (role_id,permission_id) "
                "SELECT r.id,p.id FROM identity_access.roles r "
                "CROSS JOIN identity_access.permissions p "
                "WHERE r.code=:role_code AND p.code = ANY(CAST(:permission_codes AS text[]))"
            ),
            {"role_code": role_code, "permission_codes": sorted(codes)},
        )

    bind.execute(
        sa.text(
            "UPDATE identity_access.roles SET version=version+1, updated_at=CURRENT_TIMESTAMP "
            "WHERE code = ANY(CAST(:role_codes AS text[]))"
        ),
        {"role_codes": role_codes},
    )


def downgrade() -> None:
    # The canonical state at 0005 is already this exact matrix. Restoring an
    # unknown, drifted local state would be unsafe, so no data change is made.
    pass
