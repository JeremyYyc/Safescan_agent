#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"

compose=(docker compose --env-file .env.example)
database_name="property_migration_roundtrip"
baseline_database_url="${DATABASE_URL%/*}/${database_name}"

drop_roundtrip_database() {
  "${compose[@]}" exec -T db dropdb --if-exists --force \
    --username "${POSTGRES_USER}" "${database_name}" >/dev/null
}

trap drop_roundtrip_database EXIT
drop_roundtrip_database
"${compose[@]}" exec -T db createdb --username "${POSTGRES_USER}" "${database_name}"

run_alembic() {
  "${compose[@]}" run --rm --no-deps \
    -e DATABASE_URL="${baseline_database_url}" migrations alembic "$@"
}

run_psql() {
  "${compose[@]}" exec -T db psql --set ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${database_name}" "$@"
}

run_alembic upgrade 20260908_0002

run_psql <<'SQL'
INSERT INTO property_leasing.buildings (reference, name, address, status, attributes)
VALUES ('B-LEGACY', 'Legacy Building', '1 Baseline Street', 'active', '{}'::jsonb);

INSERT INTO property_leasing.properties
    (building_id, reference, address, bedrooms, bathrooms, weekly_rent, currency, status,
     listing_visibility, attributes)
SELECT id, 'P-LEGACY-A', 'Unit A', 2, 1, 600, 'AUD', 'inactive', 'private',
       '{"cover_image_url":"https://cdn.example/p-a.jpg","floorplan_url":"https://cdn.example/p-a-plan.jpg"}'::jsonb
FROM property_leasing.buildings WHERE reference = 'B-LEGACY'
UNION ALL
SELECT id, 'P-LEGACY-B', 'Unit B', 1, 1, 500, 'AUD', 'inactive', 'private', '{}'::jsonb
FROM property_leasing.buildings WHERE reference = 'B-LEGACY';

INSERT INTO property_leasing.parties (public_id, party_type, name, contact, status)
VALUES
    ('10000000-0000-0000-0000-000000000001', 'person', 'Mapped Prospect', '{}'::jsonb, 'active'),
    ('10000000-0000-0000-0000-000000000002', 'person', 'Unmapped Prospect', '{}'::jsonb, 'active');

INSERT INTO property_leasing.leases
    (property_id, reference, starts_on, ends_on, weekly_rent, currency, status, ended_at)
SELECT id, 'L-LEGACY-MAPPED', DATE '2025-01-10', DATE '2025-12-31', 600, 'AUD', 'ended',
       TIMESTAMPTZ '2026-01-01 00:00:00+00'
FROM property_leasing.properties WHERE reference = 'P-LEGACY-A'
UNION ALL
SELECT id, 'L-LEGACY-UNMAPPED', DATE '2024-01-10', DATE '2024-12-31', 500, 'AUD', 'ended',
       TIMESTAMPTZ '2025-01-01 00:00:00+00'
FROM property_leasing.properties WHERE reference = 'P-LEGACY-B';

INSERT INTO property_leasing.prospect_cases
    (public_id, prospect_party_id, stage, status, opened_at, converted_lease_id, converted_at,
     closed_at)
SELECT '20000000-0000-0000-0000-000000000001'::uuid, party.id, 'converted', 'closed',
       TIMESTAMPTZ '2024-12-01 00:00:00+00', lease.id,
       TIMESTAMPTZ '2025-01-01 00:00:00+00', TIMESTAMPTZ '2025-01-01 00:00:00+00'
FROM property_leasing.parties AS party
JOIN property_leasing.leases AS lease ON lease.reference = 'L-LEGACY-MAPPED'
WHERE party.public_id = '10000000-0000-0000-0000-000000000001'
UNION ALL
SELECT '20000000-0000-0000-0000-000000000002'::uuid, party.id, 'contacted', 'open',
       TIMESTAMPTZ '2025-02-01 00:00:00+00', NULL, NULL, NULL
FROM property_leasing.parties AS party
WHERE party.public_id = '10000000-0000-0000-0000-000000000002';

INSERT INTO property_leasing.tenancy_applications
    (prospect_case_id, property_id, applicant_id, reference, status, submitted_at, decided_at,
     created_at)
SELECT prospect_case.id, property.id, party.id, 'APP-LEGACY-MAPPED', 'approved',
       TIMESTAMPTZ '2024-12-05 10:00:00+00', TIMESTAMPTZ '2024-12-08 10:00:00+00',
       TIMESTAMPTZ '2024-12-04 10:00:00+00'
FROM property_leasing.prospect_cases AS prospect_case
JOIN property_leasing.properties AS property ON property.reference = 'P-LEGACY-A'
JOIN property_leasing.parties AS party
  ON party.public_id = '10000000-0000-0000-0000-000000000001'
WHERE prospect_case.public_id = '20000000-0000-0000-0000-000000000001';

INSERT INTO property_leasing.lease_tenants (lease_id, party_id, signing_status)
SELECT lease.id, party.id, 'pending'
FROM property_leasing.leases AS lease
JOIN property_leasing.parties AS party
  ON (lease.reference = 'L-LEGACY-MAPPED'
      AND party.public_id = '10000000-0000-0000-0000-000000000001')
    OR (lease.reference = 'L-LEGACY-UNMAPPED'
        AND party.public_id = '10000000-0000-0000-0000-000000000002');
SQL

assert_upgraded_data() {
  run_psql <<'SQL'
DO $$
DECLARE
    mapped_property_id bigint;
    mapped_application_id bigint;
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '20260910_0007' THEN
        RAISE EXCEPTION 'unexpected upgraded revision';
    END IF;
    IF (SELECT count(*) FROM property_leasing.prospect_cases) <> 2
       OR (SELECT count(*) FROM property_leasing.leases) <> 2
       OR (SELECT count(*) FROM property_leasing.tenancy_applications) <> 1 THEN
        RAISE EXCEPTION 'baseline rows were not preserved';
    END IF;

    SELECT id INTO mapped_property_id
    FROM property_leasing.properties WHERE reference = 'P-LEGACY-A';
    SELECT id INTO mapped_application_id
    FROM property_leasing.tenancy_applications WHERE reference = 'APP-LEGACY-MAPPED';

    IF (SELECT property_id FROM property_leasing.prospect_cases
        WHERE public_id = '20000000-0000-0000-0000-000000000001')
       IS DISTINCT FROM mapped_property_id THEN
        RAISE EXCEPTION 'authoritative case property was not backfilled';
    END IF;
    IF (SELECT property_id FROM property_leasing.prospect_cases
        WHERE public_id = '20000000-0000-0000-0000-000000000002') IS NOT NULL THEN
        RAISE EXCEPTION 'unmapped case was assigned a guessed property';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM property_leasing.tenancy_applications
        WHERE reference = 'APP-LEGACY-MAPPED'
          AND desired_start_on = DATE '2024-12-05'
          AND term_months = 12
          AND occupants = 1
    ) THEN
        RAISE EXCEPTION 'legacy application compatibility terms were not backfilled';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM property_leasing.properties
        WHERE reference = 'P-LEGACY-A'
          AND display_image_urls = '["https://cdn.example/p-a.jpg"]'::jsonb
          AND floorplan_url = 'https://cdn.example/p-a-plan.jpg'
          AND parking_spaces IS NULL
    ) THEN
        RAISE EXCEPTION 'legacy property presentation metadata was not migrated safely';
    END IF;
    IF (SELECT application_id FROM property_leasing.leases
        WHERE reference = 'L-LEGACY-MAPPED') IS DISTINCT FROM mapped_application_id THEN
        RAISE EXCEPTION 'authoritative lease application was not backfilled';
    END IF;
    IF (SELECT application_id FROM property_leasing.leases
        WHERE reference = 'L-LEGACY-UNMAPPED') IS NOT NULL THEN
        RAISE EXCEPTION 'unmapped lease was assigned a guessed application';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname IN ('prospect_cases_property_required', 'leases_application_required')
        GROUP BY convalidated
        HAVING convalidated = false AND count(*) = 2
    ) THEN
        RAISE EXCEPTION 'phased required-field constraints are missing or validated';
    END IF;

    BEGIN
        INSERT INTO property_leasing.prospect_cases
            (prospect_party_id, stage, status, opened_at)
        SELECT prospect_party_id, 'new', 'open', CURRENT_TIMESTAMP
        FROM property_leasing.prospect_cases LIMIT 1;
        RAISE EXCEPTION 'new property-less case was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO property_leasing.leases
            (property_id, reference, starts_on, ends_on, weekly_rent, currency, status)
        VALUES (mapped_property_id, 'L-INVALID-NO-APPLICATION', DATE '2027-01-01',
                DATE '2027-12-31', 600, 'AUD', 'draft');
        RAISE EXCEPTION 'new application-less lease was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END $$;
SQL
}

run_alembic upgrade 20260910_0006
run_psql <<'SQL'
DO $$
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '20260910_0006' THEN
        RAISE EXCEPTION 'unexpected pre-metadata revision';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'property_leasing' AND table_name = 'properties'
          AND column_name IN ('parking_spaces', 'floor_area_sqm', 'latitude', 'longitude',
                              'display_image_urls', 'floorplan_url')
    ) THEN
        RAISE EXCEPTION 'metadata columns leaked into the published migration chain';
    END IF;
END $$;
SQL

run_alembic upgrade 20260910_0007
assert_upgraded_data

run_alembic downgrade 20260910_0006
run_psql <<'SQL'
DO $$
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '20260910_0006' THEN
        RAISE EXCEPTION 'unexpected downgraded revision';
    END IF;
    IF (SELECT count(*) FROM property_leasing.prospect_cases) <> 2
       OR (SELECT count(*) FROM property_leasing.leases) <> 2
       OR (SELECT count(*) FROM property_leasing.tenancy_applications) <> 1 THEN
        RAISE EXCEPTION 'baseline rows were not preserved by downgrade';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'property_leasing'
          AND table_name = 'properties' AND column_name IN
                ('parking_spaces', 'floor_area_sqm', 'latitude', 'longitude',
                 'display_image_urls', 'floorplan_url')
    ) THEN
        RAISE EXCEPTION 'property metadata columns remained after downgrade';
    END IF;
END $$;
SQL

run_alembic upgrade 20260910_0007
assert_upgraded_data

echo "Property metadata 0006-to-0007 migration round-trip passed."
