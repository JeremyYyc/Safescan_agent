from pathlib import Path
import re


MIGRATION = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "20260913_0009_report_property_p0.py"


def source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_revision_chain_is_coordinator_assigned() -> None:
    value = source()
    assert 'revision = "20260913_0009"' in value
    assert 'down_revision = "20260910_0007"' in value


def test_migration_changes_only_inspection_report_schema() -> None:
    value = source()
    assert 'SCHEMA = "inspection_report"' in value
    assert not re.search(r'(identity_access|property_leasing|maintenance)\.', value)


def test_database_guards_and_durable_tables_are_declared() -> None:
    value = source()
    for token in (
        "formal_ownership", "customer_lease_required",
        "report_idempotency_records", "report_audit_events",
        "uq_report_jobs_one_active_report", "reports_ownership_immutable",
        "next_event_sequence",
    ):
        assert token in value


def test_upgrade_and_downgrade_are_explicit() -> None:
    value = source()
    assert "def upgrade()" in value
    assert "def downgrade()" in value
    assert 'op.drop_table("report_idempotency_records"' in value
