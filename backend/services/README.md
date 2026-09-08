# Backend service migration roots

This directory reserves the target deployment boundaries documented in
`docs/backend/architecture/service-boundaries.md`. The running baseline remains in `backend/app` until
an entire use-case slice and its tests are moved. Do not copy code here while the old path still writes
the same data.

Each service follows `controllers -> services -> mappers -> models` and owns only its documented schema.
