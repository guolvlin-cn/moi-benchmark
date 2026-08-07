#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
compose_file="${repo_root}/local-rag-platforms/ragflow_local/compose.yaml"
env_file="${repo_root}/.local-services/ragflow_local/compose/runtime.env"
evidence_dir="${repo_root}/.local-services/ragflow_local/logs/trial-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$evidence_dir"

compose=(docker compose --project-name moi_ragflow_local --env-file "$env_file" -f "$compose_file")
"${compose[@]}" ps --all --format json >"$evidence_dir/compose-ps.json"
"${compose[@]}" logs --no-color --timestamps >"$evidence_dir/compose.log" 2>&1 || true
curl --silent --show-error --max-time 10 -D "$evidence_dir/health.headers" \
  http://127.0.0.1:9380/api/v1/system/healthz >"$evidence_dir/health.body" 2>"$evidence_dir/health.stderr" || true
docker stats --no-stream --format '{{json .}}' $("${compose[@]}" ps -q) \
  >"$evidence_dir/docker-stats.jsonl" 2>"$evidence_dir/docker-stats.stderr" || true
colima ssh -- free -h >"$evidence_dir/vm-memory.txt"
colima ssh -- df -h /var/lib/docker >"$evidence_dir/vm-disk.txt"
shasum -a 256 "$evidence_dir"/* >"$evidence_dir/SHA256SUMS"
printf '%s\n' "$evidence_dir"
