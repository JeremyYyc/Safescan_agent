"""Allow Portal service clients to exchange delegated domain tokens."""

import json

from alembic import op
import sqlalchemy as sa


revision = "20260910_0005"
down_revision = "20260910_0004"
branch_labels = None
depends_on = None


PORTAL_CLIENT_SCOPES = {
    "staff-portal": {
        "identity:subject_read",
        "identity:token_exchange",
        "identity:token_introspect",
        "application:manage",
        "application:manage_all",
        "building:read_all",
        "building:read_assigned",
        "lease:execute",
        "lease:manage_active_assigned",
        "lease:manage_all",
        "lease:prepare",
        "maintenance:assign_assigned",
        "maintenance:manage_all",
        "maintenance:update_assigned",
        "property:manage_assigned",
        "property:read_all",
        "property:read_market",
        "property:read_work_context",
        "prospect:manage",
        "prospect:manage_all",
        "report:generate_all",
        "report:generate_assigned",
        "report:read_all",
        "report:read_assigned",
        "report:read_work_context",
        "scope:manage",
        "work_order:evidence_write",
        "work_order:read_assigned",
        "work_order:update_assigned",
    },
    "tenant-portal": {
        "identity:subject_read",
        "identity:token_exchange",
        "identity:token_introspect",
        "application:self:create",
        "application:self:read",
        "application:self:submit",
        "lease:self:read",
        "lease:self:read_history",
        "maintenance:self:create",
        "property:read_market",
        "prospect:self:manage",
        "report:self:create",
        "report:self:read",
        "report:self:read_history",
    },
}

DOWNSTREAM_AUDIENCES = {
    "inspection-report-service",
    "maintenance-service",
    "property-leasing-service",
}
INTERNAL_AUDIENCE = "safescan-identity-internal"


def upgrade() -> None:
    bind = op.get_bind()
    audiences = json.dumps(sorted(DOWNSTREAM_AUDIENCES | {INTERNAL_AUDIENCE}))
    for client_code, scopes in PORTAL_CLIENT_SCOPES.items():
        result = bind.execute(
            sa.text(
                "UPDATE identity_access.service_clients "
                "SET allowed_audiences=CAST(:audiences AS jsonb), "
                "allowed_scopes=CAST(:scopes AS jsonb), version=version+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE client_code=:client_code"
            ),
            {
                "client_code": client_code,
                "audiences": audiences,
                "scopes": json.dumps(sorted(scopes)),
            },
        )
        if result.rowcount != 1:
            raise RuntimeError(f"Missing seeded Portal service client: {client_code}")


def downgrade() -> None:
    bind = op.get_bind()
    identity_scopes = json.dumps(
        ["identity:subject_read", "identity:token_exchange", "identity:token_introspect"]
    )
    for client_code in PORTAL_CLIENT_SCOPES:
        bind.execute(
            sa.text(
                "UPDATE identity_access.service_clients "
                "SET allowed_audiences=CAST(:audiences AS jsonb), "
                "allowed_scopes=CAST(:scopes AS jsonb), version=version+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE client_code=:client_code"
            ),
            {
                "client_code": client_code,
                "audiences": json.dumps([INTERNAL_AUDIENCE]),
                "scopes": identity_scopes,
            },
        )
