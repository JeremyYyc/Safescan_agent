from pathlib import Path

import pytest

pytestmark = pytest.mark.migration


CONTAINER_MIGRATION = Path("/migrations/20260914_0011_maintenance_p0.py")
MIGRATION = (
    CONTAINER_MIGRATION
    if CONTAINER_MIGRATION.exists()
    else Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "20260914_0011_maintenance_p0.py"
)


def test_revision_chain_and_schema_ownership():
    text = MIGRATION.read_text()
    assert 'revision = "20260914_0011"' in text
    assert 'down_revision = "20260914_0010"' in text
    assert 'SCHEMA = "maintenance"' in text
    assert "property_leasing." not in text
    assert "identity_access." not in text


def test_migration_declares_concurrency_and_audit_guards():
    text = MIGRATION.read_text()
    for value in (
        "idempotency_records",
        "uq_maintenance_events_order_sequence",
        "maintenance_order_assignment_consistent",
        "subject_deletion_records",
        "lease_id",
        "reported_by_subject_id",
        "description",
        "def downgrade()",
    ):
        assert value in text
