FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY astra-smoke-workload /usr/local/bin/astra-smoke-workload
COPY TASK.md /app/TASK.md
RUN chmod 0555 /usr/local/bin/astra-smoke-workload \
    && chmod 0444 /app/TASK.md

WORKDIR /app
