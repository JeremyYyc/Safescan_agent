# property-leasing-service

FastAPI data owner for buildings, properties, prospects, contact threads, applications, leases,
lease documents/signatures, and the P0 read-only billing projection. Its only public surface is the
internal `/internal/v1` contract documented in `docs/backend/api/property-leasing-api.md`.

## Consistency model

- `leases.application_id UNIQUE` makes an approved application single-use.
- `customer_lease_slots.customer_subject_id PRIMARY KEY` reserves exactly one
  `pending_signature|executed|active` lease per Identity subject.
- PostgreSQL `btree_gist` and `ex_property_active_date_overlap` reject overlapping current leases.
- Lease execution locks the lease, subject slot, property, applications, and cases in stable order;
  the winning transition, losing application/case/draft-lease closure, and outbox events commit in
  one transaction.
- Redis only caches reconstructable public market views. A Redis failure always falls back to
  PostgreSQL and cannot weaken a lease rule.

The service never accepts `tenant_subject_id` when creating a lease. It locks the approved
application and resolves `application.applicant_id -> parties.subject_id`, then fail-closed checks
the Identity SubjectProjection before preparing or sending a contract.

## Workers

`python -m app.lifecycle_worker` uses `FOR UPDATE SKIP LOCKED` for offer expiry, start-date
activation, and natural end processing. There are deliberately no P0 HTTP endpoints for early
termination or natural ending. `python -m app.outbox_worker` dispatches committed events with
retry/backoff; undeliverable events stay in PostgreSQL.

`python -m app.backfill_lease_pdfs` materializes all existing lease document versions into private
MinIO objects and exits nonzero if any document fails. Rerunning is safe: object keys include a
hash of the lease data, signature audit events, renderer version and jurisdiction's official form.
`python -m app.backfill_lease_pdfs --watch` repeats every 300 seconds. Compose keeps
`property-leasing-document-worker` behind the explicit `data-sync` profile; normal deployment
does not start content synchronization. Use `python scripts/data/sync.py --steps lease-pdf --apply`
for a manual pass, or explicitly opt into that profile for continuous scanning.
Each pass prints `scanned`, `generated`, `existing` and `failed` counts. It neither changes signed
terms/digests nor creates signatures. PDF generation uses in-memory streams.

Lease PDFs contain personalized record sheets followed by the complete official state form.
Missing lessor, bond and payment information is explicitly marked, and synthetic source records
are labeled as demonstration data. These display copies are not completed statutory forms or
signed originals. Pinned source forms and provenance live in `app/resources/lease_templates/`.
An unsupported or ambiguous state address fails explicitly rather than using another state's form.

The API lazily repairs a missing current PDF after normal lease authorization:
`GET /internal/v1/leases/{lease_id}/documents/current/pdf`. Staff and tenant BFFs proxy this as
`GET /api/v1/{staff|tenant}/leases/{lease_id}/document/pdf` with bearer authentication and
`Cache-Control: private, no-store`. Browsers receive PDF bytes; object keys and S3 credentials are
never returned. The existing JSON document endpoint remains unchanged for signing.

Objects use the configured `MINIO_REPORTS_BUCKET` and
`lease-contracts/{lease_id}/{document_id}/v{version}-{fingerprint}.pdf`. Both API and worker access
MinIO through `gateway:9000`, using the existing root `MINIO_*` configuration. No public bucket or
presigned public link is created.

## Identity service authentication

The API and outbox worker use the shared service-token provider to exchange the
`property-leasing` client ID and `IDENTITY_CLIENT_SECRET` with Identity for short-lived tokens.
They request only the `identity:subject_read` and `identity:customer_status_write` scopes; Identity
checks the service-client database allowlist on every exchange. Tokens refresh before expiry and
once after a 401. Production startup fails if the client secret is absent or too short. Readiness
also performs a real Identity call, so an invalid credential, audience, scope, or unavailable
Identity dependency makes the API `not_ready`.

## Local verification

```sh
docker build -f backend/services/property-leasing-service/Dockerfile \
  --target test -t safescan-property-leasing-test backend
docker run --rm safescan-property-leasing-test
```

Set `TEST_DATABASE_URL` against a migrated PostgreSQL 17 database to additionally run the
transaction and concurrent-constraint tests. `PROPERTY_LEASING_SEED=true` idempotently creates four
buildings and two public marketing rooms in each building for local/demo environments.
