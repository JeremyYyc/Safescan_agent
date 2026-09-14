#!/usr/bin/env bash
set -Eeuo pipefail

service_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "${service_dir}/compose.test.yml")

run_alembic() {
  "${compose[@]}" run --rm --no-deps migrations alembic "$@"
}

run_psql() {
  "${compose[@]}" exec -T postgres psql --set ON_ERROR_STOP=1 --username report --dbname report_test "$@"
}

# This project is disposable by construction (report_test). Recreate it instead of
# crossing the published Identity migration's intentionally irreversible downgrade.
"${compose[@]}" exec -T postgres psql --set ON_ERROR_STOP=1 --username report --dbname postgres <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='report_test' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS report_test;
CREATE DATABASE report_test OWNER report;
SQL
run_alembic upgrade 20260913_0009

run_psql <<'SQL'
INSERT INTO inspection_report.reports
    (public_id, created_by_subject_id, report_kind, source, title, status,
     schema_version, pipeline_version)
VALUES
    ('10000000-0000-0000-0000-000000000001',
     '20000000-0000-0000-0000-000000000001',
     'analysis', 'video_analysis', 'Preserved legacy report', 'active', 1, 'legacy-v1');

DO $$
BEGIN
  IF (SELECT count(*) FROM inspection_report.reports WHERE NOT is_formal) <> 1 THEN
    RAISE EXCEPTION 'legacy report was not preserved as compatibility data';
  END IF;
  BEGIN
    INSERT INTO inspection_report.reports
        (created_by_subject_id, created_by_account_type, is_formal, report_kind,
         source, title, status, schema_version, pipeline_version)
    VALUES
        ('20000000-0000-0000-0000-000000000002', 'staff', true, 'analysis',
         'video_analysis', 'Invalid propertyless report', 'draft', 1, 'test');
    RAISE EXCEPTION 'propertyless formal report was accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    INSERT INTO inspection_report.reports
        (property_id, created_by_subject_id, created_by_account_type, is_formal,
         report_kind, source, title, status, schema_version, pipeline_version)
    VALUES
        ('30000000-0000-0000-0000-000000000001',
         '20000000-0000-0000-0000-000000000003', 'customer', true,
         'analysis', 'video_analysis', 'Invalid leaseless tenant report', 'draft', 1, 'test');
    RAISE EXCEPTION 'leaseless formal tenant report was accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END $$;
SQL

run_alembic downgrade 20260910_0007
run_psql -c "SELECT 1 / (count(*) = 1)::int FROM inspection_report.reports WHERE title='Preserved legacy report'"
run_alembic upgrade 20260913_0009
run_psql -c "SELECT 1 / (count(*) = 1)::int FROM inspection_report.reports WHERE title='Preserved legacy report' AND NOT is_formal"

echo "Inspection Report empty upgrade, target downgrade, data preservation and re-upgrade passed."
