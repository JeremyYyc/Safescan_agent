# tenant-portal-api

Target BFF for guest, prospect and tenant-facing APIs. It owns no business database. See
`docs/backend/services/portal-apis.md`.

Product and API contracts:

- `docs/PRD-NON-AGENT-MVP.zh-CN.md`
- `docs/backend/api/tenant-portal-api.md`

## Runtime and contract

This stateless FastAPI BFF listens on port 8007. Public market reads accept guests; all private
routes validate a customer token. Customer status is only a coarse capability ceiling: the BFF
derives lease/property identifiers for maintenance and report writes, while the domain service
must re-check the active lease and ownership relation. Agent data is deliberately a bootstrap
placeholder only.

The generated machine contract is `docs/backend/openapi/tenant-portal-api.json`; regenerate it
with `python export_openapi.py`. Pooled downstream clients support `httpx.MockTransport`.
Private cache keys include subject, auth/status versions, customer status, permissions, and query
variation. Public market data uses a separate guest projection. Writes invalidate the subject
namespace, and Redis failure never bypasses domain authorization.

Run locally with `uvicorn app.main:app --port 8007`. Run tests from this directory with
`pytest -q` after installing `requirements-dev.txt`.
