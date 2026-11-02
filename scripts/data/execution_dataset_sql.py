"""Append-only PostgreSQL staging import; conflicts abort the complete transaction."""
import json
from complete_property_fields import ENRICHED_UNIT_KEYS


DEFINITIONS = {
    "media_assets": """id text PRIMARY KEY CHECK(length(id)=64), bucket text NOT NULL, object_key text NOT NULL,
mime_type text NOT NULL, byte_size bigint NOT NULL CHECK(byte_size>0), width integer NOT NULL,
height integer NOT NULL, source_url text, metadata jsonb NOT NULL, UNIQUE(bucket,object_key)""",
    "housing_records": """id text PRIMARY KEY, dataset_type text NOT NULL CHECK(dataset_type IN ('student','general')),
name text NOT NULL, city text, region text, address jsonb, source_url text, metadata jsonb NOT NULL""",
    "housing_media": """housing_id text REFERENCES collected_data.housing_records(id),
media_id text REFERENCES collected_data.media_assets(id), role text, PRIMARY KEY(housing_id,media_id)""",
    "execution_units": """id text PRIMARY KEY, housing_id text NOT NULL REFERENCES collected_data.housing_records(id),
scenario_status text NOT NULL CHECK(scenario_status IN ('active','reserved','vacant')),
weekly_rent numeric(14,2) NOT NULL CHECK(weekly_rent>0),
is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL""",
    "simulated_residents": "id text PRIMARY KEY, is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL",
    "simulated_tenancies": """id text PRIMARY KEY, unit_id text NOT NULL REFERENCES collected_data.execution_units(id),
resident_id text NOT NULL REFERENCES collected_data.simulated_residents(id), starts_on date NOT NULL,
ends_on date NOT NULL CHECK(ends_on>=starts_on), status text NOT NULL CHECK(status IN ('ended','active','executed')),
weekly_rent numeric(14,2) NOT NULL CHECK(weekly_rent>0), is_synthetic boolean NOT NULL CHECK(is_synthetic),
payload jsonb NOT NULL, UNIQUE(id,unit_id)""",
    "simulated_inspections": """id text PRIMARY KEY, unit_id text NOT NULL REFERENCES collected_data.execution_units(id),
tenancy_id text NOT NULL, kind text NOT NULL CHECK(kind IN ('move_in','routine','move_out')),
status text NOT NULL CHECK(status IN ('planned','completed')), scheduled_at timestamptz NOT NULL,
completed_at timestamptz, is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL,
FOREIGN KEY(tenancy_id,unit_id) REFERENCES collected_data.simulated_tenancies(id,unit_id),
CHECK((status='planned' AND completed_at IS NULL) OR (status='completed' AND completed_at IS NOT NULL)), UNIQUE(id,unit_id)""",
    "simulated_work_orders": """id text PRIMARY KEY, unit_id text NOT NULL REFERENCES collected_data.execution_units(id),
tenancy_id text NOT NULL, inspection_id text, priority text NOT NULL CHECK(priority IN ('low','normal','high','urgent')),
status text NOT NULL CHECK(status IN ('open','assigned','in_progress','blocked','completed','cancelled')),
reported_at timestamptz NOT NULL, completed_at timestamptz, cancelled_at timestamptz,
cost_aud numeric(14,2) NOT NULL CHECK(cost_aud>=0), is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL,
FOREIGN KEY(tenancy_id,unit_id) REFERENCES collected_data.simulated_tenancies(id,unit_id),
FOREIGN KEY(inspection_id,unit_id) REFERENCES collected_data.simulated_inspections(id,unit_id),
CHECK((status='completed')=(completed_at IS NOT NULL)), CHECK((status='cancelled')=(cancelled_at IS NOT NULL)),
CHECK(completed_at IS NULL OR completed_at>=reported_at), CHECK(cancelled_at IS NULL OR cancelled_at>=reported_at), UNIQUE(id,unit_id)""",
    "simulated_findings": """id text PRIMARY KEY, inspection_id text NOT NULL, unit_id text NOT NULL REFERENCES collected_data.execution_units(id),
tenancy_id text NOT NULL, work_order_id text NOT NULL, severity text NOT NULL CHECK(severity IN ('info','low','medium','high','critical')),
is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL,
FOREIGN KEY(inspection_id,unit_id) REFERENCES collected_data.simulated_inspections(id,unit_id),
FOREIGN KEY(tenancy_id,unit_id) REFERENCES collected_data.simulated_tenancies(id,unit_id),
FOREIGN KEY(work_order_id,unit_id) REFERENCES collected_data.simulated_work_orders(id,unit_id)""",
    "simulated_work_order_events": """id text PRIMARY KEY, work_order_id text NOT NULL REFERENCES collected_data.simulated_work_orders(id),
sequence_no integer NOT NULL CHECK(sequence_no>0), occurred_at timestamptz NOT NULL,
is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL, UNIQUE(work_order_id,sequence_no)""",
    "execution_scenarios": """id text PRIMARY KEY, unit_id text NOT NULL REFERENCES collected_data.execution_units(id),
is_synthetic boolean NOT NULL CHECK(is_synthetic), payload jsonb NOT NULL""",
}
INDEXES = {
    "housing_media": [("media_id",)],
    "execution_units": [("housing_id",)],
    "simulated_tenancies": [("unit_id", "starts_on", "ends_on"), ("resident_id",)],
    "simulated_inspections": [("unit_id", "scheduled_at"), ("tenancy_id", "unit_id")],
    "simulated_work_orders": [("unit_id", "status"), ("tenancy_id", "unit_id"), ("inspection_id", "unit_id")],
    "simulated_findings": [("inspection_id", "unit_id"), ("tenancy_id", "unit_id"), ("work_order_id", "unit_id"), ("unit_id",)],
    "execution_scenarios": [("unit_id",)],
}
FIELDS = {
    "media_assets": ("id", "bucket", "object_key", "mime_type", "byte_size", "width", "height", "source_url", "metadata"),
    "housing_records": ("id", "dataset_type", "name", "city", "region", "address", "source_url", "metadata"),
    "housing_media": ("housing_id", "media_id", "role"),
    "execution_units": ("id", "housing_id", "scenario_status", "weekly_rent", "is_synthetic", "payload"),
    "simulated_residents": ("id", "is_synthetic", "payload"),
    "simulated_tenancies": ("id", "unit_id", "resident_id", "starts_on", "ends_on", "status", "weekly_rent", "is_synthetic", "payload"),
    "simulated_inspections": ("id", "unit_id", "tenancy_id", "kind", "status", "scheduled_at", "completed_at", "is_synthetic", "payload"),
    "simulated_work_orders": ("id", "unit_id", "tenancy_id", "inspection_id", "priority", "status", "reported_at", "completed_at", "cancelled_at", "cost_aud", "is_synthetic", "payload"),
    "simulated_findings": ("id", "inspection_id", "unit_id", "tenancy_id", "work_order_id", "severity", "is_synthetic", "payload"),
    "simulated_work_order_events": ("id", "work_order_id", "sequence_no", "occurred_at", "is_synthetic", "payload"),
    "execution_scenarios": ("id", "unit_id", "is_synthetic", "payload"),
}


def literal(value, json_value=False):
    if value is None:
        return "NULL"
    if json_value:
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def export_sql(path, tables):
    with path.open("w", encoding="utf-8") as out:
        out.write("-- PostgreSQL 17. Public housing facts + explicitly simulated execution fixtures.\n"
                  "-- No identity_access/property_leasing/maintenance/inspection_report business-table writes.\n"
                  "BEGIN;\nSET LOCAL standard_conforming_strings=on;\nCREATE SCHEMA IF NOT EXISTS collected_data;\n"
                  "-- Serialize concurrent imports of this dataset without blocking ordinary readers.\n"
                  "SELECT pg_advisory_xact_lock(12608026,31);\n")
        for name, definition in DEFINITIONS.items():
            out.write(f"CREATE TABLE IF NOT EXISTS collected_data.{name} ({definition});\n")
        for name, columns_list in INDEXES.items():
            for columns in columns_list:
                # Stable short names avoid PostgreSQL's silent 63-byte identifier truncation.
                import hashlib
                suffix = hashlib.sha256((name + str(columns)).encode()).hexdigest()[:12]
                out.write(f"CREATE INDEX IF NOT EXISTS ix_au26_{suffix} ON collected_data.{name} ({','.join(columns)});\n")
        for name in DEFINITIONS:
            columns = FIELDS[name]
            keys = ("housing_id", "media_id") if name == "housing_media" else ("id",)
            out.write(f"CREATE TEMP TABLE stage_{name} (LIKE collected_data.{name} INCLUDING DEFAULTS) ON COMMIT DROP;\n")
            rows = tables[name]
            for start in range(0, len(rows), 200):
                batch = []
                for row in rows[start:start + 200]:
                    values = []
                    for column in columns:
                        value = row if column == "payload" else row.get(column)
                        values.append(literal(value, column in ("metadata", "payload", "address")))
                    batch.append("(" + ",".join(values) + ")")
                out.write(f"INSERT INTO stage_{name} ({','.join(columns)}) VALUES\n" + ",\n".join(batch) + ";\n")
            out.write(f"INSERT INTO collected_data.{name} ({','.join(columns)}) SELECT {','.join(columns)} FROM stage_{name} ON CONFLICT DO NOTHING;\n")
            if name == "execution_units":
                # The user authorized filling the previous dataset's unknown housing
                # attributes. Upgrade only the recognized v1 payload; immutable source
                # facts, IDs, rent and every unrelated key must still match exactly.
                permitted = "ARRAY[" + ",".join(literal(k) for k in ENRICHED_UNIT_KEYS) + "]::text[]"
                out.write(f"UPDATE collected_data.execution_units t SET payload=s.payload FROM stage_execution_units s "
                          f"WHERE t.id=s.id AND NOT (t.payload ? 'property_fields_version') "
                          f"AND t.payload-{permitted}=s.payload-{permitted};\n")
            if name == "simulated_tenancies":
                # Correct the per-room / whole-property label when resolved room
                # counts clarify the rental scope, preserving all dates and money.
                out.write("UPDATE collected_data.simulated_tenancies t SET payload=s.payload FROM stage_simulated_tenancies s "
                          "WHERE t.id=s.id AND t.payload-'rent_basis'=s.payload-'rent_basis' "
                          "AND EXISTS (SELECT 1 FROM collected_data.execution_units u WHERE u.id=t.unit_id "
                          "AND u.payload->>'property_fields_version'='2');\n")
            join = " AND ".join(f"t.{k}=s.{k}" for k in keys)
            left = "ROW(" + ",".join("t." + c for c in columns) + ")"
            right = "ROW(" + ",".join("s." + c for c in columns) + ")"
            out.write(f"DO $guard$ BEGIN IF EXISTS (SELECT 1 FROM stage_{name} s LEFT JOIN collected_data.{name} t ON {join} "
                      f"WHERE t.{keys[0]} IS NULL OR {left} IS DISTINCT FROM {right}) THEN "
                      f"RAISE EXCEPTION 'Dataset conflict in collected_data.{name}; existing rows were not overwritten'; END IF; END $guard$;\n")
        # Validate against already-imported tenancies as well as this batch.
        out.write("""DO $guard$ BEGIN
IF EXISTS (
 SELECT 1 FROM collected_data.simulated_tenancies a
 JOIN collected_data.simulated_tenancies b ON a.unit_id=b.unit_id AND a.id<b.id
 WHERE daterange(a.starts_on,a.ends_on,'[]') && daterange(b.starts_on,b.ends_on,'[]')
 AND EXISTS (SELECT 1 FROM stage_execution_units s WHERE s.id=a.unit_id)
) THEN RAISE EXCEPTION 'Overlapping simulated tenancies'; END IF;
END $guard$;
CREATE OR REPLACE VIEW collected_data.execution_property_profiles AS
SELECT id, housing_id, payload->>'address' AS address, payload->>'property_type' AS property_type,
 payload->>'rental_scope' AS rental_scope, (payload->>'bedrooms')::integer AS bedrooms,
 (payload->>'bathrooms')::numeric AS bathrooms, (payload->>'rooms_count')::integer AS rooms_count,
 (payload->>'parking_spaces')::integer AS parking_spaces, (payload->>'floor_area_sqm')::numeric AS floor_area_sqm,
 (payload->>'whole_apartment_bedrooms')::integer AS whole_apartment_bedrooms,
 (payload->>'whole_apartment_bathrooms')::numeric AS whole_apartment_bathrooms,
 payload->'property_field_sources' AS field_sources
FROM collected_data.execution_units;
COMMIT;
""")
