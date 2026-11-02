# Database migration target

This directory is reserved for the service-owned database layout described in
`docs/backend/data/README.md`, following the APLP separation of application code and database assets.

During the migration phase, the executable source of truth remains:

- `backend/alembic/` for revisions;
- `backend/app/persistence/target_schema.py` for target metadata;
- `backend/tests/target_schema_invariants.sql` for database invariants.

Do not duplicate revisions here. Move one schema only when its owning service receives its complete
migration chain and CI coverage.

## Current data delivery

Business data synchronization is manual. See
[the synchronization entry point](../scripts/data/README.md) for preview and execution commands.
Docker startup applies schema migrations but does not seed staff, import datasets or backfill lease PDFs.

The current Australia execution delivery contains public housing source snapshots and explicitly
simulated execution units with linked tenancies, inspections and work orders. Its source directory
is supplied to the manual sync command; large raw media/exports are not bundled into application images.
[The integration inventory](../docs/integration/2026-11-02/data-inventory.json) records checksums
of the local delivery before integration. It is an audit record, not an automatic import trigger.

City assignment and staff qualification are documented in
[city assignment](../docs/backend/data/city-assignment.md). Data reconciliation must be invoked explicitly.
