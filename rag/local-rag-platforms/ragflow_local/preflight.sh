#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
evidence_dir="${repo_root}/.local-services/ragflow_local/logs/preflight-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$evidence_dir"

docker_info="$(docker info --format '{{.Architecture}} {{.NCPU}} {{.MemTotal}}')"
read -r docker_arch docker_cpus docker_mem_bytes <<<"$docker_info"
docker_mem_gib=$((docker_mem_bytes / 1024 / 1024 / 1024))
docker_free_kib="$(colima ssh -- df -Pk /var/lib/docker | awk 'NR==2 {print $4}')"
docker_free_gib=$((docker_free_kib / 1024 / 1024))
emulation="unavailable"
if colima ssh -- test -e /proc/sys/fs/binfmt_misc/qemu-x86_64; then
  emulation="qemu-x86_64"
fi

ragflow_platform="$(docker image inspect infiniflow/ragflow:v0.26.4 --format '{{.Os}}/{{.Architecture}}')"
running_ragflow="$(docker ps --filter 'name=moi_ragflow_local' --format '{{.Names}}' | paste -sd, -)"
running_dify="$(docker ps --filter 'name=moi_dify_local' --format '{{.Names}}' | paste -sd, -)"

status="READY_FOR_CONTROLLED_TRIAL"
reason=""
if [[ "$docker_cpus" -lt 4 || "$docker_mem_gib" -lt 16 || "$docker_free_gib" -lt 50 ]]; then
  status="BLOCKED_LOCAL_RESOURCES"
  reason="upstream prerequisites require >=4 CPUs, >=16 GiB RAM, and >=50 GiB free disk"
elif [[ "$docker_arch" != "amd64" && "$ragflow_platform" == "linux/amd64" && "$emulation" == "unavailable" ]]; then
  status="BLOCKED_LOCAL_ARCH"
  reason="amd64-only RAGFlow image has no local x86_64 binfmt emulator"
fi

jq -n \
  --arg recorded_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg status "$status" \
  --arg reason "$reason" \
  --arg docker_arch "$docker_arch" \
  --argjson docker_cpus "$docker_cpus" \
  --argjson docker_mem_gib "$docker_mem_gib" \
  --argjson docker_free_gib "$docker_free_gib" \
  --arg emulation "$emulation" \
  --arg ragflow_platform "$ragflow_platform" \
  --arg running_ragflow "$running_ragflow" \
  --arg running_dify "$running_dify" \
  '{recorded_at:$recorded_at,status:$status,reason:$reason,host:{docker_arch:$docker_arch,cpus:$docker_cpus,memory_gib:$docker_mem_gib,docker_free_gib:$docker_free_gib,emulation:$emulation},ragflow_image_platform:$ragflow_platform,running:{ragflow:$running_ragflow,dify:$running_dify}}' \
  | tee "$evidence_dir/preflight.json"

docker image inspect \
  infiniflow/ragflow:v0.26.4 elasticsearch:8.11.3 mysql:8.0.39 \
  pgsty/minio:RELEASE.2026-03-25T00-00-00Z valkey/valkey:8 \
  >"$evidence_dir/local-image-inspect.json"
docker ps --no-trunc >"$evidence_dir/docker-ps.txt"
shasum -a 256 "$evidence_dir"/* >"$evidence_dir/SHA256SUMS"

if [[ "$status" == "BLOCKED_LOCAL_RESOURCES" ]]; then
  exit 42
fi
if [[ "$status" == "BLOCKED_LOCAL_ARCH" ]]; then
  exit 43
fi
