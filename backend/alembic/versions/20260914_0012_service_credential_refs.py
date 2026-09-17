"""Point P0 service clients at environment-backed credential references.

Revision ID: 20260914_0012
Revises: 20260914_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260914_0012"
down_revision = "20260914_0011"
branch_labels = None
depends_on = None


CLIENTS = (
    "staff-portal", "tenant-portal", "property-leasing", "maintenance", "inspection-report",
)


def _environment_name(client_code: str) -> str:
    return "IDENTITY_SERVICE_CREDENTIAL_" + client_code.upper().replace("-", "_")


def upgrade() -> None:
    bind = op.get_bind()
    for client_code in CLIENTS:
        result = bind.execute(sa.text(
            "UPDATE identity_access.service_clients SET credential_ref=:credential_ref, "
            "version=version+1, updated_at=CURRENT_TIMESTAMP WHERE client_code=:client_code"
        ), {"client_code": client_code,
            "credential_ref": f"env://{_environment_name(client_code)}"})
        if result.rowcount != 1:
            raise RuntimeError(f"Missing seeded Identity service client: {client_code}")


def downgrade() -> None:
    bind = op.get_bind()
    for client_code in CLIENTS:
        bind.execute(sa.text(
            "UPDATE identity_access.service_clients SET credential_ref=:credential_ref, "
            "version=GREATEST(version-1,1), updated_at=CURRENT_TIMESTAMP "
            "WHERE client_code=:client_code AND credential_ref=:current_ref"
        ), {"client_code": client_code,
            "credential_ref": f"seed://identity-p0/{client_code}",
            "current_ref": f"env://{_environment_name(client_code)}"})
