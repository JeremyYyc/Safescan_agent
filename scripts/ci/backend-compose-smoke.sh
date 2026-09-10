#!/usr/bin/env bash
set -Eeuo pipefail

export APP_ENV="${APP_ENV:-ci}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-safescan-local-smoke}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://safescan_ci:safescan_ci_password@db:5432/safescan_ci}"
export POSTGRES_DB="${POSTGRES_DB:-safescan_ci}"
export POSTGRES_USER="${POSTGRES_USER:-safescan_ci}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-safescan_ci_password}"
export AUTH_SECRET="${AUTH_SECRET:-ci-auth-secret-not-for-production}"
export PUBLIC_ID_SECRET="${PUBLIC_ID_SECRET:-ci-public-id-secret-not-for-production}"
export IDENTITY_EXPOSE_ACTION_TOKENS="${IDENTITY_EXPOSE_ACTION_TOKENS:-true}"
export IDENTITY_SEED_STAFF="${IDENTITY_SEED_STAFF:-true}"
export IDENTITY_DELETION_PEPPER="${IDENTITY_DELETION_PEPPER:-ci-deletion-pepper-not-for-production}"
export PROPERTY_LEASING_SEED="${PROPERTY_LEASING_SEED:-true}"
export REDIS_PASSWORD="${REDIS_PASSWORD:-safescan-ci-redis-password}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-safescan-ci}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-safescan-ci-secret}"
export MINIO_BROWSER_REDIRECT_URL="${MINIO_BROWSER_REDIRECT_URL:-http://127.0.0.1:19001}"
export GATEWAY_PORT="${GATEWAY_PORT:-18080}"
export GATEWAY_S3_PORT="${GATEWAY_S3_PORT:-19000}"
export GATEWAY_CONSOLE_PORT="${GATEWAY_CONSOLE_PORT:-19001}"

compose=(docker compose --env-file .env.example)
base_url="http://127.0.0.1:${GATEWAY_PORT}"
tenant_file="/tmp/${COMPOSE_PROJECT_NAME}-tenant.html"
staff_file="/tmp/${COMPOSE_PROJECT_NAME}-staff.html"
not_found_file="/tmp/${COMPOSE_PROJECT_NAME}-not-found.json"

"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db
"${compose[@]}" run --rm --no-deps migrations

expected_revisions="$(
  "${compose[@]}" run --rm --no-deps migrations alembic heads |
    awk '$NF == "(head)" { print $1 }'
)"
head_count="$(printf '%s\n' "${expected_revisions}" | awk 'NF { count++ } END { print count + 0 }')"
if [[ "${head_count}" -ne 1 ]]; then
  echo "Expected exactly one Alembic head, found ${head_count}: ${expected_revisions}" >&2
  exit 1
fi
expected_revision="${expected_revisions}"

revision="$("${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -At -c 'SELECT version_num FROM alembic_version')"
test "${revision}" = "${expected_revision}"

"${compose[@]}" run --rm --no-deps migrations alembic downgrade 20260908_0002
revision="$("${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -At -c 'SELECT version_num FROM alembic_version')"
test "${revision}" = "20260908_0002"

"${compose[@]}" run --rm --no-deps migrations alembic upgrade head
revision="$("${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -At -c 'SELECT version_num FROM alembic_version')"
test "${revision}" = "${expected_revision}"

portal_scopes() {
  "${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
    -c "SELECT allowed_scopes::text FROM identity_access.service_clients WHERE client_code='$1'"
}

export PORTAL_SERVICE_SCOPES="$(portal_scopes staff-portal)"
export STAFF_PORTAL_SERVICE_TOKEN="$(
  python3 scripts/ci/issue-portal-service-token.py staff-portal
)"
export PORTAL_SERVICE_SCOPES="$(portal_scopes tenant-portal)"
export TENANT_PORTAL_SERVICE_TOKEN="$(
  python3 scripts/ci/issue-portal-service-token.py tenant-portal
)"
unset PORTAL_SERVICE_SCOPES

"${compose[@]}" up -d --no-build --wait --wait-timeout 240 \
  db redis minio identity-access-service \
  property-leasing-service maintenance-service inspection-report-service \
  inspection-report-worker staff-portal-api tenant-portal-api \
  staff-web tenant-web gateway

curl --fail --silent --show-error --retry 20 --retry-all-errors --retry-connrefused \
  --retry-delay 2 "${base_url}/gateway-health" >/dev/null
curl --fail --silent --show-error --location "${base_url}/" >"${tenant_file}"
curl --fail --silent --show-error "${base_url}/staff/" >"${staff_file}"
grep -q "SafeScan Tenant Portal" "${tenant_file}"
grep -q "SafeScan 员工工作台" "${staff_file}"

curl --fail --silent --show-error -H 'Content-Type: application/json' -d '{}' \
  "${base_url}/api/v1/auth/guest-sessions" >/dev/null

staff_counts="$("${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -At -c "SELECT r.code || ':' || count(*) FROM identity_access.staff s JOIN identity_access.roles r ON r.id=s.role_id JOIN identity_access.users u ON u.id=s.user_id WHERE u.status='active' AND s.employment_status='active' GROUP BY r.code ORDER BY r.code")"
test "${staff_counts}" = "$(printf '%s\n' \
  'leasing_consultant:4' 'maintainer:3' 'manager_admin:1' 'property_manager:4')"

hashed_staff="$("${compose[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -At -c "SELECT count(*) FROM identity_access.user_credentials c JOIN identity_access.users u ON u.id=c.user_id WHERE u.account_type='staff' AND c.algorithm='argon2id' AND c.secret_hash LIKE '\$argon2id\$%'")"
test "${hashed_staff}" = "12"

python3 scripts/ci/identity-api-smoke.py "${base_url}"
python3 scripts/ci/portal-bff-api-smoke.py "${base_url}"

not_found_status="$(curl --silent --show-error -o "${not_found_file}" -w '%{http_code}' \
  "${base_url}/api/v1/staff/not-yet-implemented")"
test "${not_found_status}" = "404"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1], encoding="utf-8"))["error"]["code"] == "resource_not_found"' \
  "${not_found_file}"

for service_port in \
  property-leasing-service:8002 maintenance-service:8003 \
  inspection-report-service:8004 staff-portal-api:8006 tenant-portal-api:8007; do
  service="${service_port%%:*}"
  port="${service_port##*:}"
  "${compose[@]}" exec -T "${service}" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${port}/health/ready', timeout=2)"
done

"${compose[@]}" exec -T redis redis-cli -a "${REDIS_PASSWORD}" ping | grep -q PONG

for service in db redis minio identity-access-service property-leasing-service \
  maintenance-service inspection-report-service inspection-report-worker \
  staff-portal-api tenant-portal-api staff-web tenant-web gateway; do
  "${compose[@]}" ps --status running --services | \
    awk -v expected="${service}" '$0 == expected { found=1 } END { exit !found }'
done

echo "P0 Docker Compose skeleton smoke test passed."
