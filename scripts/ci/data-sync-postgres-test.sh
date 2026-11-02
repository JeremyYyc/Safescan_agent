#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${COMPOSE_PROJECT_NAME:?COMPOSE_PROJECT_NAME is required}"
compose=(docker compose --env-file .env.example)
database_name="manual_sync_test"
database_url="${DATABASE_URL%/*}/${database_name}"

cleanup() {
  "${compose[@]}" exec -T db dropdb --if-exists --force \
    --username "${POSTGRES_USER}" "${database_name}" >/dev/null
}
trap cleanup EXIT
cleanup
"${compose[@]}" exec -T db createdb --username "${POSTGRES_USER}" "${database_name}"
"${compose[@]}" run --rm --no-deps -e DATABASE_URL="${database_url}" \
  migrations alembic upgrade head
"${compose[@]}" run --rm --no-deps -e IDENTITY_DATABASE_URL="${database_url}" \
  -e IDENTITY_SEED_STAFF=true --entrypoint python identity-access-service -m app.seed_staff
docker run --rm --network "${COMPOSE_PROJECT_NAME}_database" \
  -e TEST_DATABASE_URL="${database_url}" -e PROPERTY_LEASING_DATABASE_URL="${database_url}" \
  -e PYTHONPATH=/workspace/scripts/data:/app \
  -v "$PWD:/workspace:ro" -w /workspace/scripts/data \
  safescan-property-leasing-test pytest -q -p no:cacheprovider test_sync_postgres.py
