"""Complete the P0 maintenance order aggregate."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260914_0011"
down_revision = "20260914_0010"
branch_labels = None
depends_on = None

SCHEMA = "maintenance"


def upgrade() -> None:
    op.add_column("maintenance_orders", sa.Column("lease_id", UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("maintenance_orders", sa.Column("reported_by_subject_id", UUID(as_uuid=True)),
                  schema=SCHEMA)
    op.add_column("maintenance_orders", sa.Column("description", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_orders", sa.Column("completed_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("maintenance_orders", sa.Column("cancelled_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("maintenance_orders", sa.Column("next_event_sequence", sa.BigInteger(), nullable=False,
                                                   server_default="1"), schema=SCHEMA)
    op.execute(
        "UPDATE maintenance.maintenance_orders SET "
        "completed_at=COALESCE(completed_at,updated_at,created_at) WHERE status='completed'"
    )
    op.execute(
        "UPDATE maintenance.maintenance_orders SET "
        "cancelled_at=COALESCE(cancelled_at,updated_at,created_at) WHERE status='cancelled'"
    )
    op.create_check_constraint(
        "maintenance_order_assignment_consistent", "maintenance_orders",
        "status NOT IN ('assigned','in_progress','blocked','completed') OR "
        "(assigned_staff_id IS NOT NULL AND assigned_by_staff_id IS NOT NULL AND assigned_at IS NOT NULL)",
        schema=SCHEMA, postgresql_not_valid=True,
    )
    op.create_index("ix_maintenance_orders_reporter_created", "maintenance_orders",
                    ["reported_by_subject_id", "created_at", "id"], schema=SCHEMA)
    op.create_index("ix_maintenance_orders_property_created", "maintenance_orders",
                    ["property_id", "created_at", "id"], schema=SCHEMA)
    op.create_index("ix_maintenance_orders_assignee_created", "maintenance_orders",
                    ["assigned_staff_id", "created_at", "id"], schema=SCHEMA)
    op.create_check_constraint(
        "maintenance_order_terminal_time_consistent", "maintenance_orders",
        "(status <> 'completed' OR completed_at IS NOT NULL) AND "
        "(status <> 'cancelled' OR cancelled_at IS NOT NULL)", schema=SCHEMA,
    )

    op.add_column("maintenance_events", sa.Column("public_id", UUID(as_uuid=True), nullable=False,
                                                   server_default=sa.text("gen_random_uuid()")),
                  schema=SCHEMA)
    op.create_unique_constraint("uq_maintenance_events_public_id", "maintenance_events",
                                ["public_id"], schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("sequence_no", sa.BigInteger()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("actor_subject_id", UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("actor_type", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("visibility", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("message", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("from_status", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("to_status", sa.Text()), schema=SCHEMA)
    op.add_column("maintenance_events", sa.Column("client_message_id", UUID(as_uuid=True)), schema=SCHEMA)
    op.execute(
        """
        WITH ranked AS (
          SELECT id, row_number() OVER (PARTITION BY order_id ORDER BY created_at, id) AS sequence_no
          FROM maintenance.maintenance_events
        )
        UPDATE maintenance.maintenance_events e
        SET sequence_no = ranked.sequence_no,
            actor_type = CASE WHEN e.actor_staff_id IS NULL THEN 'system' ELSE 'staff' END,
            visibility = 'internal'
        FROM ranked WHERE ranked.id = e.id
        """
    )
    op.alter_column("maintenance_events", "sequence_no", nullable=False, schema=SCHEMA)
    op.alter_column("maintenance_events", "actor_type", nullable=False, schema=SCHEMA)
    op.alter_column("maintenance_events", "visibility", nullable=False, schema=SCHEMA)
    op.execute(
        """
        UPDATE maintenance.maintenance_orders o
        SET next_event_sequence = COALESCE(events.next_sequence, 1)
        FROM (
          SELECT order_id, max(sequence_no) + 1 AS next_sequence
          FROM maintenance.maintenance_events GROUP BY order_id
        ) events
        WHERE events.order_id = o.id
        """
    )
    op.create_unique_constraint("uq_maintenance_events_order_sequence", "maintenance_events",
                                ["order_id", "sequence_no"], schema=SCHEMA)
    op.create_unique_constraint("uq_maintenance_events_order_client_message", "maintenance_events",
                                ["order_id", "client_message_id"], schema=SCHEMA)
    op.create_check_constraint("maintenance_event_actor_type_valid", "maintenance_events",
                               "actor_type IN ('customer','staff','system')", schema=SCHEMA)
    op.create_check_constraint("maintenance_event_visibility_valid", "maintenance_events",
                               "visibility IN ('public','internal')", schema=SCHEMA)

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("actor_subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", JSONB()),
        sa.Column("resource_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_subject_id", "operation", "idempotency_key",
                            name="uq_maintenance_idempotency_actor_operation_key"),
        sa.CheckConstraint("response_status IS NULL OR response_status BETWEEN 200 AND 299",
                           name="maintenance_idempotency_status_valid"),
        schema=SCHEMA,
    )
    op.create_index("ix_maintenance_idempotency_expiry", "idempotency_records", ["expires_at"],
                    schema=SCHEMA)
    op.create_table(
        "subject_deletion_records",
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('completed','failed')", name="maintenance_deletion_status_valid"),
        schema=SCHEMA,
    )
    op.create_index("ix_maintenance_deletions_subject", "subject_deletion_records", ["subject_id"],
                    schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("subject_deletion_records", schema=SCHEMA)
    op.drop_index("ix_maintenance_idempotency_expiry", table_name="idempotency_records", schema=SCHEMA)
    op.drop_table("idempotency_records", schema=SCHEMA)
    op.drop_constraint("maintenance_event_visibility_valid", "maintenance_events", schema=SCHEMA, type_="check")
    op.drop_constraint("maintenance_event_actor_type_valid", "maintenance_events", schema=SCHEMA, type_="check")
    op.drop_constraint("uq_maintenance_events_order_client_message", "maintenance_events", schema=SCHEMA,
                       type_="unique")
    op.drop_constraint("uq_maintenance_events_order_sequence", "maintenance_events", schema=SCHEMA,
                       type_="unique")
    op.drop_constraint("uq_maintenance_events_public_id", "maintenance_events", schema=SCHEMA,
                       type_="unique")
    for column in ("client_message_id", "to_status", "from_status", "message", "visibility",
                   "actor_type", "actor_subject_id", "sequence_no", "public_id"):
        op.drop_column("maintenance_events", column, schema=SCHEMA)
    op.drop_constraint("maintenance_order_terminal_time_consistent", "maintenance_orders", schema=SCHEMA,
                       type_="check")
    op.drop_constraint("maintenance_order_assignment_consistent", "maintenance_orders", schema=SCHEMA,
                       type_="check")
    op.drop_index("ix_maintenance_orders_assignee_created", table_name="maintenance_orders", schema=SCHEMA)
    op.drop_index("ix_maintenance_orders_property_created", table_name="maintenance_orders", schema=SCHEMA)
    op.drop_index("ix_maintenance_orders_reporter_created", table_name="maintenance_orders", schema=SCHEMA)
    for column in ("next_event_sequence", "cancelled_at", "completed_at", "description",
                   "reported_by_subject_id", "lease_id"):
        op.drop_column("maintenance_orders", column, schema=SCHEMA)
