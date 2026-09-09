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

## Local verification

```sh
docker build -f backend/services/property-leasing-service/Dockerfile \
  --target test -t safescan-property-leasing-test backend
docker run --rm safescan-property-leasing-test
```

Set `TEST_DATABASE_URL` against a migrated PostgreSQL 17 database to additionally run the
transaction and concurrent-constraint tests. `PROPERTY_LEASING_SEED=true` idempotently creates four
buildings and two public marketing rooms in each building for local/demo environments.
