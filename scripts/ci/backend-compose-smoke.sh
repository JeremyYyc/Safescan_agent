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
export IDENTITY_BOOTSTRAP_ADMIN_EMAIL="${IDENTITY_BOOTSTRAP_ADMIN_EMAIL:-ci.admin@example.com}"
export IDENTITY_BOOTSTRAP_ADMIN_PASSWORD="${IDENTITY_BOOTSTRAP_ADMIN_PASSWORD:-CiAdmin123!Password}"
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

"${compose[@]}" up -d --no-build --wait --wait-timeout 240 \
  db redis minio migrations identity-access-service \
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

not_found_status="$(curl --silent --show-error -o "${not_found_file}" -w '%{http_code}' \
  "${base_url}/api/v1/staff/not-yet-implemented")"
test "${not_found_status}" = "404"
grep -q '"code": "resource_not_found"' "${not_found_file}"

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
