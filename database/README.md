# Database migration target

This directory is reserved for the service-owned database layout described in
`docs/backend/data/README.md`, following the APLP separation of application code and database assets.

During the migration phase, the executable source of truth remains:

- `backend/alembic/` for revisions;
- `backend/app/persistence/target_schema.py` for target metadata;
- `backend/tests/target_schema_invariants.sql` for database invariants.

Do not duplicate revisions here. Move one schema only when its owning service receives its complete
migration chain and CI coverage.
