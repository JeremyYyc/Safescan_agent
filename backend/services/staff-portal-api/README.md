# staff-portal-api

Target BFF for deterministic staff-facing APIs. It owns no business database. See
`docs/backend/services/portal-apis.md`.

Product and API contracts:

- `docs/PRD-NON-AGENT-MVP.zh-CN.md`
- `docs/backend/api/staff-portal-api.md`

## Runtime and contract

This is a stateless FastAPI BFF on port 8006. It validates staff JWT audience/account type,
performs coarse role pre-checks, exchanges the browser token through Identity, and calls the
Property Leasing, Maintenance, and Inspection Report internal APIs with pooled HTTP clients.
The domain services remain responsible for final resource authorization and every state change.

The generated machine contract is `docs/backend/openapi/staff-portal-api.json`; regenerate it
with `python export_openapi.py`. The four downstream clients accept `httpx.MockTransport` for
consumer-contract tests. Private read cache keys include subject, auth/role versions, role,
permissions, scopes, projection, and query variation; successful writes invalidate the subject
namespace. Redis failure degrades reads to an uncached request and never grants authorization.

Run locally with `uvicorn app.main:app --port 8006`. Run tests from this directory with
`pytest -q` after installing `requirements-dev.txt`.
