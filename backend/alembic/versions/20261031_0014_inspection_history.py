"""Preserve lease ownership and import provenance for inspection histories."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261031_0014"
down_revision = "20260914_0013"
branch_labels = None
depends_on = None


def upgrade():
    # The baseline creates the current target metadata on a fresh database.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("inspections", schema="inspection_report")}
    if "source_lease_id" not in columns:
        op.add_column("inspections", sa.Column("source_lease_id", UUID(as_uuid=True)), schema="inspection_report")
    if "attributes" not in columns:
        op.add_column("inspections", sa.Column("attributes", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), schema="inspection_report")
    if "ix_inspections_lease_recent" not in {index["name"] for index in inspector.get_indexes("inspections", schema="inspection_report")}:
        op.create_index("ix_inspections_lease_recent", "inspections", ["source_lease_id", "inspected_at", "id"], schema="inspection_report")


def downgrade():
    op.drop_index("ix_inspections_lease_recent", table_name="inspections", schema="inspection_report")
    op.drop_column("inspections", "attributes", schema="inspection_report")
    op.drop_column("inspections", "source_lease_id", schema="inspection_report")
