# safescan-common

Versioned shared Python distribution for stable cross-cutting infrastructure.

Implemented modules:

- `safescan_common.http`: API errors, response envelopes, request IDs,
  FastAPI exception handlers, health routers and cursor pagination.
- `safescan_common.database`: SQLAlchemy engine/session factories, request
  dependencies and transactional session scopes.
- `safescan_common.auth`: principal contract, JWT consumer verification and
  scope dependencies.

Install for local development with `pip install -e backend/packages/safescan-common`.
Docker services install the package from the shared `backend` build context.

It must not contain ORM models or business rules. The import package is named
`safescan_common` and follows semantic versioning as more services adopt it.
