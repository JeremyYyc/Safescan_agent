#!/usr/bin/env bash
set -Eeuo pipefail

export APP_ENV="${APP_ENV:-ci}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-safescan-local-smoke}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://safescan_ci:safescan_ci_password@db:5432/safescan_ci}"
export POSTGRES_DB="${POSTGRES_DB:-safescan_ci}"
export POSTGRES_USER="${POSTGRES_USER:-safescan_ci}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-safescan_ci_password}"
export POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-15432}"
export AUTH_SECRET="${AUTH_SECRET:-ci-auth-secret-not-for-production}"
export PUBLIC_ID_SECRET="${PUBLIC_ID_SECRET:-ci-public-id-secret-not-for-production}"
export IDENTITY_EXPOSE_ACTION_TOKENS="${IDENTITY_EXPOSE_ACTION_TOKENS:-true}"
export IDENTITY_BOOTSTRAP_ADMIN_EMAIL="${IDENTITY_BOOTSTRAP_ADMIN_EMAIL:-ci.admin@example.com}"
export IDENTITY_BOOTSTRAP_ADMIN_PASSWORD="${IDENTITY_BOOTSTRAP_ADMIN_PASSWORD:-CiAdmin123!Password}"
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-ci-model-key-not-used}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-safescan-ci}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-safescan-ci-secret}"
export MINIO_BROWSER_REDIRECT_URL="${MINIO_BROWSER_REDIRECT_URL:-http://127.0.0.1:19001}"
export GATEWAY_PORT="${GATEWAY_PORT:-18080}"
export GATEWAY_S3_PORT="${GATEWAY_S3_PORT:-19000}"
export GATEWAY_CONSOLE_PORT="${GATEWAY_CONSOLE_PORT:-19001}"

compose=(docker compose --env-file .env.example)
base_url="http://127.0.0.1:${GATEWAY_PORT}"
register_file="/tmp/${COMPOSE_PROJECT_NAME}-register.json"
refresh_file="/tmp/${COMPOSE_PROJECT_NAME}-refresh.json"
admin_file="/tmp/${COMPOSE_PROJECT_NAME}-admin.json"
roles_file="/tmp/${COMPOSE_PROJECT_NAME}-roles.json"
staff_file="/tmp/${COMPOSE_PROJECT_NAME}-staff.json"
staff_activation_file="/tmp/${COMPOSE_PROJECT_NAME}-staff-activation.json"
cookie_file="/tmp/${COMPOSE_PROJECT_NAME}-cookies.txt"

"${compose[@]}" up -d --no-build --wait --wait-timeout 180 db minio gateway frontend backend identity-access-service

curl --fail --silent --show-error \
  --retry 40 --retry-all-errors --retry-connrefused --retry-delay 2 \
  "${base_url}/gateway-health" >/dev/null
curl --fail --silent --show-error \
  --retry 40 --retry-all-errors --retry-connrefused --retry-delay 2 \
  "${base_url}/health" >/dev/null
curl --fail --silent --show-error \
  --retry 40 --retry-all-errors --retry-connrefused --retry-delay 2 \
  "${base_url}/" >/dev/null

run_id="${GITHUB_RUN_ID:-local}-$(date +%s)"
curl --fail --silent --show-error \
  --retry 40 --retry-all-errors --retry-connrefused --retry-delay 2 \
  "${base_url}/api/v1/auth/guest-sessions" \
  -H 'Content-Type: application/json' -d '{}' >/dev/null
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -c "${cookie_file}" \
  -d "{\"email\":\"ci.${run_id}@example.com\",\"username\":\"CI Smoke\",\"password\":\"CiSmoke123!Pass\",\"accepted_terms_version\":\"v1\"}" \
  "${base_url}/api/v1/auth/register" >"${register_file}"

token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["access_token"])' "${register_file}")"
test -n "${token}"

curl --fail --silent --show-error \
  -H "Authorization: Bearer ${token}" \
  "${base_url}/api/v1/me" >/dev/null

csrf="$(awk '$6 == "safescan_csrf" { print $7 }' "${cookie_file}")"
test -n "${csrf}"
curl --fail --silent --show-error \
  -b "${cookie_file}" -c "${cookie_file}" \
  -H "X-CSRF-Token: ${csrf}" \
  -X POST "${base_url}/api/v1/auth/refresh" >"${refresh_file}"
refreshed_token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["access_token"])' "${refresh_file}")"
test -n "${refreshed_token}"
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${refreshed_token}" \
  "${base_url}/api/v1/me" >/dev/null

csrf="$(awk '$6 == "safescan_csrf" { print $7 }' "${cookie_file}")"
logout_status="$(curl --silent --show-error -o /dev/null -w '%{http_code}' \
  -b "${cookie_file}" -H "X-CSRF-Token: ${csrf}" \
  -H "Authorization: Bearer ${refreshed_token}" \
  -X POST "${base_url}/api/v1/auth/logout")"
test "${logout_status}" = "204"
revoked_status="$(curl --silent --show-error -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${refreshed_token}" "${base_url}/api/v1/me")"
test "${revoked_status}" = "401"

curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${IDENTITY_BOOTSTRAP_ADMIN_EMAIL}\",\"password\":\"${IDENTITY_BOOTSTRAP_ADMIN_PASSWORD}\"}" \
  "${base_url}/api/v1/auth/login" >"${admin_file}"
admin_token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["access_token"])' "${admin_file}")"
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${admin_token}" \
  "${base_url}/api/v1/iam/roles?limit=20" >"${roles_file}"
manager_role_id="$(python3 -c 'import json,sys; print(next(x["id"] for x in json.load(open(sys.argv[1], encoding="utf-8"))["data"] if x["code"] == "manager_admin"))' "${roles_file}")"
staff_code="CI$(date +%s)"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' -H "Authorization: Bearer ${admin_token}" \
  -d "{\"email\":\"staff.${run_id}@example.com\",\"username\":\"CI Staff\",\"display_name\":\"CI Staff\",\"staff_code\":\"${staff_code}\",\"role_id\":\"${manager_role_id}\"}" \
  "${base_url}/api/v1/iam/staff" >"${staff_file}"
activation_token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["debug_action_token"])' "${staff_file}")"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"${activation_token}\",\"new_password\":\"CiStaff123!Password\"}" \
  "${base_url}/api/v1/auth/staff-activation/confirm" >"${staff_activation_file}"
staff_token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["access_token"])' "${staff_activation_file}")"
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${staff_token}" \
  "${base_url}/api/v1/me" >/dev/null

for service in db minio gateway frontend backend identity-access-service; do
  "${compose[@]}" ps --status running --services | awk -v expected="${service}" '$0 == expected { found=1 } END { exit !found }'
done

echo "Docker Compose customer and staff identity smoke test passed."
