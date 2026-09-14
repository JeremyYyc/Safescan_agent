# maintenance-service

PostgreSQL-backed P0 owner for formal maintenance orders and their append-only timeline.

## Runtime

The service listens on port 8003. It requires `DATABASE_URL`, `AUTH_SECRET`, controlled
Identity/Property Leasing base URLs and service credentials. It never reads another service's
schema. Browser clients use the Staff/Tenant Portal BFFs; all routes here are internal.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8003
pytest -q
python export_openapi.py
```

Contract: `docs/backend/api/maintenance-api.md`. Migration:
`20260914_0011_maintenance_p0.py` (`down_revision=20260914_0010`, Identity delegation prerequisite).
Agent draft and attachment
routes remain disabled for P0.

## P0 authorization

| Actor | Read/list | Write |
|---|---|---|
| Tenant | Orders whose `reported_by_subject_id` is the verified actor | Create only after two active-Lease relationship checks; edit/comment/cancel own eligible order |
| Property Manager | Orders whose Property is accepted by Property Leasing scope authorization | Assign an active Maintainer; edit, comment, or run allowed transitions in scope |
| Maintainer | Orders whose `assigned_staff_id` is the verified staff public ID | Comment and transition only the assigned order |
| Manager Admin | All orders | Same state, version, idempotency, and audit rules as other staff |

Private missing and unauthorized resources both return `404 resource_not_found`. Staff, role,
customer status, and subject values are read only from the verified actor token. Maintenance uses
its Identity service credential to exchange the incoming Maintenance actor token for a zero-scope,
`property-leasing-service` audience actor token before every Lease/Property authorization check.
It never forwards the incoming token and never reads another service schema.

## State and consistency

Assignment moves `open → assigned`; allowed transition commands are `assigned → in_progress`,
`in_progress → blocked|completed|cancelled`, `blocked → in_progress|completed|cancelled`, plus
the frozen early cancellation paths. Every command locks the aggregate, checks `version`, increments
it, appends a monotonic timeline event, and writes a transactionally consistent outbox event.
`Idempotency-Key + actor + operation` is persisted and protected with a PostgreSQL advisory lock.

## Tests

The non-PostgreSQL suite includes domain, API producer contract, migration declaration, and mocked
HTTP adapter tests. The tests marked `postgres_integration` and `concurrency` require
`TEST_DATABASE_URL` and use PostgreSQL for constraints, row locks, idempotency races, timeline order,
and account-deletion blockers. The Compose smoke is a real Portal → Identity token exchange →
Maintenance → Identity re-delegation → Property Leasing authorization flow. Only the explicitly
marked adapter tests mock Identity/Property responses.
