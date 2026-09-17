#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"

compose=(docker compose --env-file .env.example)
database_name="maintenance_migration_roundtrip"
roundtrip_url="${DATABASE_URL%/*}/${database_name}"

cleanup() {
  "${compose[@]}" exec -T db dropdb --if-exists --force \
    --username "${POSTGRES_USER}" "${database_name}" >/dev/null
}

trap cleanup EXIT
cleanup
"${compose[@]}" exec -T db createdb --username "${POSTGRES_USER}" "${database_name}"

run_alembic() {
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL="${roundtrip_url}" migrations alembic "$@"
}

run_psql() {
  "${compose[@]}" exec -T db psql --set ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${database_name}" "$@"
}

run_alembic upgrade 20260914_0011
run_psql <<'SQL'
DO $$
BEGIN
  IF (SELECT version_num FROM alembic_version) <> '20260914_0011' THEN
    RAISE EXCEPTION 'unexpected Maintenance revision';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='maintenance' AND table_name='idempotency_records'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='maintenance' AND table_name='maintenance_orders'
      AND column_name='reported_by_subject_id'
  ) THEN
    RAISE EXCEPTION 'Maintenance P0 schema is incomplete';
  END IF;
END $$;
SQL

run_alembic downgrade 20260914_0010
run_psql <<'SQL'
DO $$
BEGIN
  IF (SELECT version_num FROM alembic_version) <> '20260914_0010' THEN
    RAISE EXCEPTION 'unexpected Maintenance downgrade revision';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='maintenance' AND table_name='maintenance_orders'
  ) OR EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='maintenance' AND table_name='idempotency_records'
  ) THEN
    RAISE EXCEPTION 'Maintenance downgrade boundary is invalid';
  END IF;
END $$;
SQL

run_alembic upgrade 20260914_0011
run_psql -c "SELECT 1 / (count(*) = 1)::int FROM alembic_version WHERE version_num='20260914_0011'"

echo "Maintenance empty upgrade, target downgrade, and re-upgrade passed."
