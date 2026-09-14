"""Allow trusted domain services to re-delegate actor tokens safely.

Revision ID: 20260914_0010
Revises: 20260913_0009
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20260914_0010"
down_revision = "20260913_0009"
branch_labels = None
depends_on = None


DOMAIN_DELEGATION = {
    "maintenance": {
        "audiences": {"property-leasing-service"},
        "scopes": {
            "identity:token_exchange",
            "maintenance:assign_assigned",
            "maintenance:manage_all",
            "maintenance:self:create",
            "maintenance:update_assigned",
            "property:manage_assigned",
            "property:read_all",
            "property:read_market",
            "property:read_work_context",
            "work_order:evidence_write",
            "work_order:read_assigned",
            "work_order:update_assigned",
        },
    },
    "inspection-report": {
        "audiences": {"property-leasing-service", "maintenance-service"},
        "scopes": {
            "identity:token_exchange",
            "property:manage_assigned",
            "property:read_all",
            "property:read_market",
            "property:read_work_context",
            "report:generate_all",
            "report:generate_assigned",
            "report:read_all",
            "report:read_assigned",
            "report:read_work_context",
            "report:self:create",
            "report:self:read",
            "report:self:read_history",
            "work_order:read_assigned",
        },
    },
}

# These values are frozen by 20260908_0003 and still form the exact predecessor
# state at 20260913_0009. They document the boundary for contract tests. Upgrade
# also records the per-row set difference so downgrade removes only values this
# revision actually inserted, including when an operator preconfigured overlap.
PREDECESSOR = {
    "maintenance": {
        "audiences": {"safescan-identity-internal"},
        "scopes": {
            "identity:subject_read", "identity:subject_deletion_ack",
            "identity:subject_deletion_read", "identity:subject_tombstone_check",
        },
    },
    "inspection-report": {
        "audiences": {"safescan-identity-internal"},
        "scopes": {
            "identity:subject_read", "identity:subject_deletion_ack",
            "identity:subject_deletion_read", "identity:subject_tombstone_check",
        },
    },
}
STATE_TABLE = "migration_20260914_0010_service_client_additions"


def _update(*, add: bool) -> None:
    bind = op.get_bind()
    for client_code, additions in DOMAIN_DELEGATION.items():
        row = bind.execute(
            sa.text(
                "SELECT allowed_audiences,allowed_scopes "
                "FROM identity_access.service_clients "
                "WHERE client_code=:client_code FOR UPDATE"
            ),
            {"client_code": client_code},
        ).mappings().first()
        if not row:
            raise RuntimeError(f"Missing seeded Identity service client: {client_code}")
        audiences = set(row["allowed_audiences"] or [])
        scopes = set(row["allowed_scopes"] or [])
        if add:
            added_audiences = additions["audiences"] - audiences
            added_scopes = additions["scopes"] - scopes
            bind.execute(
                sa.text(
                    f"INSERT INTO identity_access.{STATE_TABLE} "
                    "(client_code,added_audiences,added_scopes) "
                    "VALUES (:client_code,CAST(:audiences AS jsonb),CAST(:scopes AS jsonb))"
                ),
                {
                    "client_code": client_code,
                    "audiences": json.dumps(sorted(added_audiences)),
                    "scopes": json.dumps(sorted(added_scopes)),
                },
            )
            audiences.update(additions["audiences"])
            scopes.update(additions["scopes"])
        else:
            state = bind.execute(
                sa.text(
                    f"SELECT added_audiences,added_scopes FROM identity_access.{STATE_TABLE} "
                    "WHERE client_code=:client_code"
                ),
                {"client_code": client_code},
            ).mappings().one()
            audiences.difference_update(state["added_audiences"] or [])
            scopes.difference_update(state["added_scopes"] or [])
        bind.execute(
            sa.text(
                "UPDATE identity_access.service_clients "
                "SET allowed_audiences=CAST(:audiences AS jsonb), "
                "allowed_scopes=CAST(:scopes AS jsonb), version=version+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE client_code=:client_code"
            ),
            {
                "client_code": client_code,
                "audiences": json.dumps(sorted(audiences)),
                "scopes": json.dumps(sorted(scopes)),
            },
        )


def upgrade() -> None:
    op.create_table(
        STATE_TABLE,
        sa.Column("client_code", sa.Text(), primary_key=True),
        sa.Column("added_audiences", sa.JSON(), nullable=False),
        sa.Column("added_scopes", sa.JSON(), nullable=False),
        schema="identity_access",
    )
    _update(add=True)


def downgrade() -> None:
    _update(add=False)
    op.drop_table(STATE_TABLE, schema="identity_access")
