import os
from pathlib import Path


MIGRATION = Path(os.getenv("PROPERTY_MIGRATION_PATH", "/migrations/20260909_0003_property_leasing_p0.py"))
if not MIGRATION.exists():
    MIGRATION = Path(__file__).parents[3] / "alembic" / "versions" / MIGRATION.name


def test_database_guards_are_declared_in_migration() -> None:
    text = MIGRATION.read_text()
    assert "customer_lease_slots" in text
    assert "ex_property_active_date_overlap" in text
    assert "uq_leases_application_id" in text
    assert "pg_advisory_xact_lock" not in text  # request locks belong to application transaction code
    assert "def downgrade()" in text


def test_lease_grants_are_removed_by_p0_migration() -> None:
    text = MIGRATION.read_text()
    assert 'op.drop_table("lease_access_grants"' in text


def test_legacy_prospect_cases_are_migrated_without_guessing_a_property() -> None:
    text = MIGRATION.read_text()
    assert 'sa.Column("property_id", sa.BigInteger(), nullable=True)' in text
    assert "WITH property_candidates AS" in text
    assert "HAVING count(DISTINCT property_id) = 1" in text
    assert "prospect_cases_property_required CHECK (property_id IS NOT NULL) NOT VALID" in text


def test_legacy_applications_and_leases_have_explicit_migration_policy() -> None:
    text = MIGRATION.read_text()
    assert "desired_start_on = COALESCE(submitted_at::date, created_at::date)" in text
    assert "term_months = 12" in text
    assert "occupants = 1" in text
    assert "WITH lease_application_candidates AS" in text
    assert "HAVING count(DISTINCT application_id) = 1" in text
    assert "leases_application_required CHECK (application_id IS NOT NULL) NOT VALID" in text
