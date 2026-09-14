#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"

compose=(docker compose --env-file .env.example)
database_name="identity_delegation_migration_test"
database_url="${DATABASE_URL%/*}/${database_name}"

cleanup() {
  "${compose[@]}" exec -T db dropdb --if-exists --force \
    --username "${POSTGRES_USER}" "${database_name}" >/dev/null
}
trap cleanup EXIT
cleanup
"${compose[@]}" exec -T db createdb --username "${POSTGRES_USER}" "${database_name}"

alembic() {
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL="${database_url}" migrations alembic "$@"
}

psql_test() {
  "${compose[@]}" exec -T db psql --set ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${database_name}" "$@"
}

alembic upgrade 20260913_0009

psql_test <<'SQL'
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM identity_access.service_clients
    WHERE client_code IN ('maintenance','inspection-report')
      AND allowed_scopes ? 'identity:token_exchange'
  ) THEN
    RAISE EXCEPTION 'domain delegation exists before its migration';
  END IF;
END $$;

UPDATE identity_access.service_clients
SET allowed_scopes = allowed_scopes || '["identity:token_exchange"]'::jsonb
WHERE client_code = 'maintenance';
SQL

alembic upgrade 20260914_0010

psql_test <<'SQL'
DO $$
BEGIN
  IF (SELECT version_num FROM alembic_version) <> '20260914_0010' THEN
    RAISE EXCEPTION 'unexpected Identity delegation head';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM identity_access.service_clients
    WHERE client_code='maintenance'
      AND allowed_audiences ? 'property-leasing-service'
      AND allowed_scopes ?& ARRAY[
        'identity:token_exchange','maintenance:self:create','maintenance:assign_assigned',
        'maintenance:update_assigned','maintenance:manage_all','work_order:read_assigned',
        'work_order:update_assigned','work_order:evidence_write','property:read_market',
        'property:manage_assigned','property:read_all','property:read_work_context'
      ]
  ) THEN
    RAISE EXCEPTION 'maintenance delegation allowlist is incomplete';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM identity_access.service_clients
    WHERE client_code='inspection-report'
      AND allowed_audiences ?& ARRAY['property-leasing-service','maintenance-service']
      AND allowed_scopes ?& ARRAY['identity:token_exchange','work_order:read_assigned','report:read_work_context']
  ) THEN
    RAISE EXCEPTION 'inspection-report delegation allowlist is incomplete';
  END IF;
END $$;
SQL

alembic downgrade 20260913_0009

psql_test <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM identity_access.service_clients
    WHERE client_code='maintenance'
      AND allowed_scopes ? 'identity:token_exchange'
      AND NOT allowed_scopes ? 'maintenance:self:create'
      AND NOT allowed_audiences ? 'property-leasing-service'
  ) THEN
    RAISE EXCEPTION 'downgrade removed a preconfigured scope or retained migration additions';
  END IF;
  IF EXISTS (
    SELECT 1 FROM identity_access.service_clients
    WHERE client_code='inspection-report'
      AND (allowed_scopes ? 'identity:token_exchange'
           OR allowed_audiences ?| ARRAY['property-leasing-service','maintenance-service'])
  ) THEN
    RAISE EXCEPTION 'inspection-report delegation additions survived downgrade';
  END IF;
END $$;
SQL

alembic upgrade 20260914_0010
echo "Identity domain delegation migration round-trip passed."
