# Inspection Report Service

P0 property/lease-owned report API and durable PostgreSQL worker. This service owns
`inspection_report` reports, workspaces, file metadata, jobs, steps and events. It
authorizes Property and Lease relationships only through Property Leasing internal
HTTP APIs and never reads another service schema.

## Entrypoints

```bash
uvicorn inspection_report_service.main:app --host 0.0.0.0 --port 8004
python -m inspection_report_service.worker
```

Both processes use `INSPECTION_REPORT_DATABASE_URL`, private MinIO credentials and
the same `AUTH_SECRET`. Production also requires
`INSPECTION_REPORT_IDENTITY_SERVICE_TOKEN` so actor tokens can be exchanged for the
`property-leasing-service` audience. Buckets are private; callers retrieve objects
only through the authorized `/internal/v1/files/{id}/content` endpoint.

## Durable execution

API submission commits the formal report, uploaded file metadata and durable job
before returning. Workers claim with `FOR UPDATE SKIP LOCKED`, commit the lease,
heartbeat during Pipeline stages and recover expired leases. Retry is bounded and
reserved for transient failures. Cancellation is observed between existing Pipeline
stages. Event sequence numbers, steps and idempotency records are PostgreSQL state,
so API/SSE disconnects and process restarts do not remove work.

## Pipeline boundary

`ReportPipelineServices` delegates every video, model, prompt, validation, scoring
and report-writing step to the existing `backend/app` Pipeline. The adapter replaces
only authorization (already completed by the API), object metadata storage and the
final INSERT with an update of the pre-created report. Legacy callers without the
adapter retain their existing behavior. Existing PDF rendering remains the P1/legacy
compatibility path and is covered by characterization tests; this service does not
introduce a second PDF layout.

Deterministic model substitutes are allowed only in service tests and are labelled
as such. They validate orchestration and persistence, not model quality. PostgreSQL,
MinIO, authorization HTTP boundaries and claim concurrency tests use real components.

## Integration Coordinator interfaces

Shared Compose/Gateway/CI are intentionally not modified by this branch. Integration
must run the API command above plus a worker using the same image and
`python -m inspection_report_service.worker`, expose port 8004 internally, supply
database/MinIO/auth variables, and configure an Identity service token permitted to
exchange actor tokens to the Property Leasing audience. Required CI jobs must set
real `REPORT_TEST_DATABASE_URL` and `REPORT_TEST_MINIO_*` values rather than skipping
component tests.

Maintenance must implement its frozen
`POST /internal/v1/authorizations/order-access:check` contract with
`subject_id`, `order_id`, `action=report:read_work_context`, and `report_id`, returning
`allowed` plus the authoritative `property_id`. The additive report
`GET /internal/v1/reports/{report_id}/work-context?maintenance_order_id=...` endpoint
fails closed and returns only hazard/recommendation/evidence fragments; it never grants
the Maintainer full report access.
