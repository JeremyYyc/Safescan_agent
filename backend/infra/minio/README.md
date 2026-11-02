# Pinned official MinIO source build

This image replaces an unavailable upstream container tag without changing the
MinIO server/client releases or the application's private S3 storage boundary.
It builds the official repositories at the immutable commits in
`source-lock.json`; each commit was checked against its annotated release tag.
The bundled versions match the previously cached official image:

| Program | Release | Commit |
| --- | --- | --- |
| Server | `RELEASE.2025-07-23T15-54-02Z` | `7ced9663e6a791fef9dc6be798ff24cda9c730ac` |
| mc | `RELEASE.2025-07-21T05-28-08Z` | `ee72571936f15b0e65dc8b4a231a4dd445e5ccb6` |

Both binaries use Go 1.24.5, `CGO_ENABLED=0`, the official
`buildscripts/gen-ldflags.go`, the exact release timestamps and the `kqueue`
build tag used by the upstream Makefiles. The runtime includes CA certificates,
curl, both binaries, upstream licenses and the pinned upstream entrypoint.
The original image has no static `MC_HOST_local` setting: `mc ready local` uses
the client's built-in local alias. `MC_CONFIG_DIR=/tmp/.mc` is preserved.

Build from the repository root:

```sh
docker build -f backend/infra/minio/Dockerfile -t safescan-minio:RELEASE.2025-07-23T15-54-02Z backend
docker run --rm --entrypoint minio safescan-minio:RELEASE.2025-07-23T15-54-02Z --version
docker run --rm --entrypoint mc safescan-minio:RELEASE.2025-07-23T15-54-02Z --version
```

Keep the existing Compose `server /data --console-address :9001` command,
credential variables, storage network, named volume and `mc ready local`
healthcheck. Building this image does not access an existing MinIO volume.

The build needs access to Docker Official Images, GitHub and the Go module
proxy/checksum service. Its first native build downloads and compiles the server
dependency graph; warmed module/compiler caches make subsequent builds faster.
The two binaries compile sequentially with two package workers to limit CI
memory usage. Build time depends on the runner and network; this does not claim
byte-for-byte equivalence to the upstream image or a cross-platform build cache.

Official sources:

- [Server release](https://github.com/minio/minio/tree/RELEASE.2025-07-23T15-54-02Z)
- [Client release](https://github.com/minio/mc/tree/RELEASE.2025-07-21T05-28-08Z)
- [Server build flags](https://github.com/minio/minio/blob/7ced9663e6a791fef9dc6be798ff24cda9c730ac/buildscripts/gen-ldflags.go)
- [Client build flags](https://github.com/minio/mc/blob/ee72571936f15b0e65dc8b4a231a4dd445e5ccb6/buildscripts/gen-ldflags.go)
