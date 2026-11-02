# Source commits, matching annotated tags, and toolchain are recorded beside this file.
FROM golang:1.24.5-alpine3.22@sha256:daae04ebad0c21149979cd8e9db38f565ecefd8547cf4a591240dc1972cf1399 AS build

ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN apk add --no-cache ca-certificates git
WORKDIR /src

# Fetch immutable commits and keep Git metadata for the official version generator.
RUN git init minio \
    && git -C minio remote add origin https://github.com/minio/minio.git \
    && git -C minio -c http.version=HTTP/1.1 fetch --depth=1 origin 7ced9663e6a791fef9dc6be798ff24cda9c730ac \
    && git -C minio checkout --detach FETCH_HEAD \
    && test "$(git -C minio rev-parse HEAD)" = 7ced9663e6a791fef9dc6be798ff24cda9c730ac

WORKDIR /src/minio
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -p=2 -trimpath -tags kqueue \
    -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-07-23T15:54:02Z)" \
    -o /out/minio .

WORKDIR /src
RUN git init mc \
    && git -C mc remote add origin https://github.com/minio/mc.git \
    && git -C mc -c http.version=HTTP/1.1 fetch --depth=1 origin ee72571936f15b0e65dc8b4a231a4dd445e5ccb6 \
    && git -C mc checkout --detach FETCH_HEAD \
    && test "$(git -C mc rev-parse HEAD)" = ee72571936f15b0e65dc8b4a231a4dd445e5ccb6

WORKDIR /src/mc
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -p=2 -trimpath -tags kqueue \
    -ldflags "$(MC_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-07-21T05:28:08Z)" \
    -o /out/mc .

FROM alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1 AS runtime
RUN apk add --no-cache ca-certificates curl
ENV MINIO_ACCESS_KEY_FILE=access_key \
    MINIO_SECRET_KEY_FILE=secret_key \
    MINIO_ROOT_USER_FILE=access_key \
    MINIO_ROOT_PASSWORD_FILE=secret_key \
    MINIO_KMS_SECRET_KEY_FILE=kms_master_key \
    MINIO_CONFIG_ENV_FILE=config.env \
    MC_CONFIG_DIR=/tmp/.mc

COPY --from=build /out/minio /out/mc /usr/local/bin/
COPY --from=build /src/minio/dockerscripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --from=build /src/minio/LICENSE /src/minio/CREDITS /licenses/minio/
COPY --from=build /src/mc/LICENSE /licenses/mc/LICENSE
RUN chmod 0755 /usr/local/bin/minio /usr/local/bin/mc /usr/local/bin/docker-entrypoint.sh

EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["minio"]
