ARG RUNTIME_BASE_IMAGE=debian:12-slim
FROM ${RUNTIME_BASE_IMAGE} AS runtime_builder

ARG RUNTIME_BASE_IMAGE
ARG HERMES_REF=v2026.7.20
ARG HERMES_RELEASE=0.19.0
ARG HERMES_COMMIT=3ef6bbd201263d354fd83ec55b3c306ded2eb72a
ARG HERMES_INSTALLER_SHA256=c5ba7e89627577fab914514736ecfb3359b66956ca00199bfef616ca35953cb9
ARG PLAYWRIGHT_RELEASE=1.62.0
ARG HERMES_TEMPERATURE=0.0
ARG HERMES_TEMPERATURE_CONFIGURATOR_SHA256=89ed14fb6fcb4b68b25cf2fd2300037f94261649e8ab2cd64f97912c841a0f25

ENV PATH="/root/.local/bin:/usr/local/bin:${PATH}" \
    UV_MANAGED_PYTHON=1

RUN apt-get -o Acquire::Retries=5 update \
    && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        python3 \
        ripgrep \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# The upstream browser step uses an unversioned npx resolution. Skip only that
# step and immediately perform the same full install at a pinned release.
RUN --mount=type=cache,target=/root/.cache/uv \
    curl -fsSL \
        --retry 8 \
        --retry-all-errors \
        --retry-delay 5 \
        --retry-max-time 180 \
        "https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_COMMIT}/scripts/install.sh" \
        -o /tmp/hermes-install.sh \
    && printf '%s  %s\n' \
        "${HERMES_INSTALLER_SHA256}" \
        /tmp/hermes-install.sh \
        | sha256sum -c - \
    && bash /tmp/hermes-install.sh \
        --skip-setup \
        --skip-browser \
        --branch "${HERMES_REF}" \
        --commit "${HERMES_COMMIT}" \
    && cd /usr/local/lib/hermes-agent \
    && /root/.hermes/node/bin/npx --yes \
        "playwright@${PLAYWRIGHT_RELEASE}" \
        install --with-deps chromium \
    && cd / \
    && test "$(git -C /usr/local/lib/hermes-agent rev-parse HEAD)" = "${HERMES_COMMIT}" \
    && python_real="$(readlink -f \
        /usr/local/lib/hermes-agent/venv/bin/python)" \
    && case "${python_real}" in \
        /usr/local/share/uv/python/*) ;; \
        *) printf 'Hermes venv is not relocatable: %s\n' \
            "${python_real}" >&2; exit 1 ;; \
       esac \
    && test -x "${python_real}" \
    && test -x /root/.hermes/bin/uv \
    && test -x /root/.hermes/node/bin/node \
    && browser="$(find /root/.cache/ms-playwright -type f \
        \( -name chrome -o -name headless_shell \) \
        -perm -111 -print -quit)" \
    && test -n "${browser}" \
    && playwright_cli="$(find \
        /usr/local/lib/hermes-agent/node_modules \
        /root/.npm/_npx \
        -path '*/playwright-core/cli.js' \
        -type f -print -quit 2>/dev/null)" \
    && test -n "${playwright_cli}" \
    && mkdir -p /opt/moi \
    && cp -a "$(dirname "${playwright_cli}")" /opt/moi/playwright-core \
    && /root/.hermes/node/bin/node \
        -p "require('/opt/moi/playwright-core/package.json').version" \
        > /opt/moi/playwright-version \
    && test "$(cat /opt/moi/playwright-version)" = "${PLAYWRIGHT_RELEASE}" \
    && hermes version \
    && rm -f /tmp/hermes-install.sh \
    && rm -rf \
        /root/.cache/electron \
        /root/.cache/node-gyp \
        /root/.cache/rosetta \
        /root/.npm \
    && rm -rf /var/lib/apt/lists/*

COPY configure_temperature.py /tmp/configure-hermes-temperature.py

RUN printf '%s  %s\n' \
        "${HERMES_TEMPERATURE_CONFIGURATOR_SHA256}" \
        /tmp/configure-hermes-temperature.py \
        | sha256sum -c - \
    && test "${HERMES_TEMPERATURE}" = "0.0" \
    && python3 /tmp/configure-hermes-temperature.py apply \
        --repo-root /usr/local/lib/hermes-agent \
        --audit-dir /opt/moi \
        --temperature "${HERMES_TEMPERATURE}" \
    && test "$(git -C /usr/local/lib/hermes-agent diff --name-only)" \
        = "plugins/model-providers/zai/__init__.py" \
    && git -C /usr/local/lib/hermes-agent diff --check \
    && expected_temperature="$(cat /opt/moi/hermes-temperature)" \
    && actual_temperature="$(cd /usr/local/lib/hermes-agent \
        && venv/bin/python -c \
        'from providers import get_provider_profile; print(get_provider_profile("zai").fixed_temperature)')" \
    && test "${actual_temperature}" = "${expected_temperature}" \
    && python3 -c \
        'import hashlib,json; from pathlib import Path; audit=json.load(open("/opt/moi/hermes-temperature.json")); source=Path("/usr/local/lib/hermes-agent/plugins/model-providers/zai/__init__.py").read_bytes(); patch=Path("/opt/moi/hermes-temperature.patch").read_bytes(); assert audit["temperature"] == 0.0; assert audit["scope"] == "primary_zai_chat_completions"; assert hashlib.sha256(source).hexdigest() == audit["patched_source_sha256"]; assert hashlib.sha256(patch).hexdigest() == audit["patch_sha256"]' \
    && rm -f /tmp/configure-hermes-temperature.py

RUN mkdir -p /opt/moi \
    && temperature="$(cat /opt/moi/hermes-temperature)" \
    && temperature_patch_sha256="$(cat \
        /opt/moi/hermes-temperature.patch.sha256)" \
    && temperature_patched_source_sha256="$(python3 -c \
        'import json; print(json.load(open("/opt/moi/hermes-temperature.json"))["patched_source_sha256"])')" \
    && printf \
        '{"schema_version":1,"product":"hermes-agent","hermes_ref":"%s","hermes_release":"%s","source_commit":"%s","installer_sha256":"%s","playwright_release":"%s","runtime_base_image":"%s","platform":"linux/amd64","temperature":%s,"temperature_source":"provider_profile.fixed_temperature","temperature_scope":"primary_zai_chat_completions","temperature_patch_sha256":"%s","temperature_patched_source_sha256":"%s","temperature_configurator_sha256":"%s"}\n' \
        "${HERMES_REF}" \
        "${HERMES_RELEASE}" \
        "${HERMES_COMMIT}" \
        "${HERMES_INSTALLER_SHA256}" \
        "${PLAYWRIGHT_RELEASE}" \
        "${RUNTIME_BASE_IMAGE}" \
        "${temperature}" \
        "${temperature_patch_sha256}" \
        "${temperature_patched_source_sha256}" \
        "${HERMES_TEMPERATURE_CONFIGURATOR_SHA256}" \
        > /opt/moi/hermes-preinstalled.json \
    && chmod 0444 /opt/moi/hermes-preinstalled.json

# Publish only the relocatable runtime payload. The Debian build environment
# and its package-manager layers remain in BuildKit's cache, not in the shared
# runtime image consumed by every task.
FROM scratch

COPY --link --from=runtime_builder \
    /usr/local/lib/hermes-agent \
    /usr/local/lib/hermes-agent
COPY --link --from=runtime_builder \
    /usr/local/share/uv \
    /usr/local/share/uv
COPY --link --from=runtime_builder \
    /root/.hermes/node \
    /root/.hermes/node
COPY --link --from=runtime_builder \
    /root/.cache/ms-playwright \
    /root/.cache/ms-playwright
COPY --link --from=runtime_builder \
    /usr/local/bin/hermes \
    /usr/local/bin/hermes
COPY --link --from=runtime_builder \
    /opt/moi/hermes-preinstalled.json \
    /opt/moi/hermes-preinstalled.json
COPY --link --from=runtime_builder \
    /opt/moi/playwright-core \
    /opt/moi/playwright-core
COPY --link --from=runtime_builder \
    /opt/moi/playwright-version \
    /opt/moi/playwright-version
COPY --link --from=runtime_builder \
    /opt/moi/hermes-temperature \
    /opt/moi/hermes-temperature
COPY --link --from=runtime_builder \
    /opt/moi/hermes-temperature.json \
    /opt/moi/hermes-temperature.json
COPY --link --from=runtime_builder \
    /opt/moi/hermes-temperature.patch \
    /opt/moi/hermes-temperature.patch
COPY --link --from=runtime_builder \
    /opt/moi/hermes-temperature.patch.sha256 \
    /opt/moi/hermes-temperature.patch.sha256

LABEL org.opencontainers.image.title="Hermes Terminal-Bench shared runtime payload"
LABEL org.opencontainers.image.version="v2026.7.20"
LABEL org.opencontainers.image.revision="3ef6bbd201263d354fd83ec55b3c306ded2eb72a"
LABEL io.moi.hermes-tbench.kind="runtime"
ARG HERMES_TEMPERATURE=0.0
ARG HERMES_TEMPERATURE_CONFIGURATOR_SHA256=89ed14fb6fcb4b68b25cf2fd2300037f94261649e8ab2cd64f97912c841a0f25
LABEL io.moi.hermes-tbench.temperature="${HERMES_TEMPERATURE}"
LABEL io.moi.hermes-tbench.temperature-source="provider_profile.fixed_temperature"
LABEL io.moi.hermes-tbench.temperature-scope="primary_zai_chat_completions"
LABEL io.moi.hermes-tbench.temperature-patch-sha256="6b71f1395a6533af731c506ceaed3dab885b04055bd3bc05eae696ba9786339a"
LABEL io.moi.hermes-tbench.temperature-patched-source-sha256="766e0fbb7b257701323bc4a4b49697047b1b20b46f6df53d85d48314516cca0a"
LABEL io.moi.hermes-tbench.temperature-configurator-sha256="${HERMES_TEMPERATURE_CONFIGURATOR_SHA256}"
