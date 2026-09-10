# identity-access-service

Independent FastAPI deployment that owns authentication, account lifecycle,
sessions, staff/customer identities, RBAC, service clients and identity audit
events in the `identity_access` schema.

The HTTP dependency direction is `controller -> service -> mapper -> table
mapping`. Schema changes remain in the platform Alembic chain while services
are split; this service never calls another service's tables.

Cross-cutting HTTP contracts, SQLAlchemy session factories, token-consumer
verification and pagination are imported from the versioned `safescan-common`
package. Passwords, token issuance, sessions and RBAC remain owned here.

- Public ingress: `/api/v1/auth/*`, `/api/v1/me*`, `/api/v1/iam/*`
- Container-network only: `/internal/v1/*`
- Health: `/health/live`, `/health/ready`
- Container port: `8001`
- Full contract: `docs/backend/api/identity-access-api.md`

The internal API includes a service-authenticated, PII-minimal directory for
active Leasing Consultants. Property Leasing uses the list for assignment and
the detail endpoint to fail closed when a staff account, employment, or role is
no longer active; both reads require `identity:subject_read`.

For development and demo environments, `IDENTITY_SEED_STAFF=true` idempotently
creates the approved twelve active staff accounts. Their configured plaintext
bootstrap passwords are immediately converted to Argon2id hashes; existing
accounts are neither duplicated nor reset. Production rejects this setting.

Install the shared package for local development with
`pip install -e ../../packages/safescan-common`. Tests are split into explicit
CI suites:

- `pytest -m unit tests/test_contract.py` for isolated unit and contract tests;
- `TEST_DATABASE_URL=... pytest -m postgres_integration tests/test_postgres_integration.py`
  for committed PostgreSQL behavior;
- `TEST_DATABASE_URL=... pytest -m concurrency tests/test_concurrency.py` for
  duplicate-registration and refresh-rotation races.

The PostgreSQL suites require a migrated, disposable database whose name has a
`test` or `ci` segment; they intentionally refuse to run against other
databases. Repository CI also exercises customer registration, access token
validation, refresh rotation/replay protection, logout, seeded staff login and
customer tenancy-stage transitions through the Nginx gateway.
