# Local Alpine Postgres 15.2 plus pgvector. Official pgvector/pgvector:pg15
# is Debian and cannot reuse an existing Alpine 15 data volume.
FROM postgres:15.2-alpine

RUN apk add --no-cache --virtual .build-deps \
        git build-base clang14 llvm14 postgresql15-dev \
    && git clone --depth 1 --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector with_llvm=no \
    && make -C /tmp/pgvector with_llvm=no install \
    && rm -rf /tmp/pgvector \
    && apk del .build-deps
