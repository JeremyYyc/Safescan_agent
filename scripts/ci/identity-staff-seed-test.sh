#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${COMPOSE_PROJECT_NAME:?COMPOSE_PROJECT_NAME is required}"
compose=(docker compose --env-file .env.example)
database_name="identity_staff_seed_test"
database_url="${DATABASE_URL%/*}/${database_name}"

cleanup() {
  "${compose[@]}" exec -T db dropdb --if-exists --force \
    --username "${POSTGRES_USER}" "${database_name}" >/dev/null
}
trap cleanup EXIT
cleanup
"${compose[@]}" exec -T db createdb --username "${POSTGRES_USER}" "${database_name}"
"${compose[@]}" run --rm --no-deps -e DATABASE_URL="${database_url}" migrations alembic upgrade head
docker run --rm --network "${COMPOSE_PROJECT_NAME}_database" \
  -e TEST_DATABASE_URL="${database_url}" safescan-identity-test \
  pytest -q --strict-markers /app/tests/test_seed_staff.py
