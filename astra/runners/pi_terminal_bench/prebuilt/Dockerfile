ARG RUNTIME_BASE_IMAGE=debian:12-slim
FROM ${RUNTIME_BASE_IMAGE} AS runtime_builder

ARG NODE_VERSION=22.19.0
ARG PI_VERSION=0.73.1

RUN apt-get -o Acquire::Retries=5 update \
    && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        ca-certificates \
        curl \
        xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && architecture="$(dpkg --print-architecture)" \
    && case "${architecture}" in \
        amd64) node_arch=x64 ;; \
        arm64) node_arch=arm64 ;; \
        *) printf 'unsupported architecture: %s\n' "${architecture}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL --retry 8 --retry-all-errors \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" \
        -o /tmp/node.tar.xz \
    && mkdir -p /opt/pi-runtime \
    && tar -xJf /tmp/node.tar.xz --strip-components=1 -C /opt/pi-runtime \
    && PATH="/opt/pi-runtime/bin:${PATH}" /opt/pi-runtime/bin/npm install -g \
        "@mariozechner/pi-coding-agent@${PI_VERSION}" \
    && test "$(PATH="/opt/pi-runtime/bin:${PATH}" /opt/pi-runtime/bin/pi --version 2>&1 | tail -n 1)" = "${PI_VERSION}" \
    && mkdir -p /opt/moi \
    && printf \
        '{"schema_version":1,"product":"pi-coding-agent","package":"@mariozechner/pi-coding-agent","version":"%s","node_version":"%s"}\n' \
        "${PI_VERSION}" "${NODE_VERSION}" \
        > /opt/moi/pi-preinstalled.json \
    && chmod 0444 /opt/moi/pi-preinstalled.json \
    && rm -f /tmp/node.tar.xz

FROM scratch

COPY --link --from=runtime_builder /opt/pi-runtime /opt/pi-runtime
COPY --link --from=runtime_builder \
    /opt/moi/pi-preinstalled.json \
    /opt/moi/pi-preinstalled.json

LABEL org.opencontainers.image.title="Pi Terminal-Bench shared runtime payload"
LABEL org.opencontainers.image.version="0.73.1"
LABEL io.moi.pi-tbench.kind="runtime"
