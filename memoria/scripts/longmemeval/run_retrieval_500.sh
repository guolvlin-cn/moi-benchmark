#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark"
RUNTIME_ROOT="/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime"
PYTHON="/Users/wangyaqi/Documents/cursor_project/.venv/bin/python"
RUN_DIR="${PROJECT_ROOT}/memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/retrieval/top20-full500-v1"
RESTART_SERVICES=false

usage() {
  cat <<'EOF'
Usage: run_retrieval_500.sh [--restart-services]

  --restart-services  Restart only the dedicated memoria-longmemeval Compose
                      services before the formal run, preserving database data.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart-services)
      RESTART_SERVICES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "${PROJECT_ROOT}"
mkdir -p "${RUN_DIR}"

if pgrep -f 'memoria/scripts/longmemeval/ingest.py' >/dev/null; then
  echo "Refusing to start: a LongMemEval ingest process is still running." >&2
  exit 1
fi

if pgrep -f 'memoria/scripts/longmemeval/retrieve.py' >/dev/null; then
  echo "Refusing to start: another LongMemEval retrieval process is running." >&2
  exit 1
fi

if [[ "${RESTART_SERVICES}" == true ]]; then
  echo "Restarting dedicated memoria-longmemeval services before formal run."
  (
    cd "${RUNTIME_ROOT}"
    docker compose stop
    docker compose up -d
  )
fi

health_ready=false
for _ in {1..60}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8100/health >/dev/null; then
    health_ready=true
    break
  fi
  sleep 2
done
if [[ "${health_ready}" != true ]]; then
  echo "Memoria health check did not become ready." >&2
  exit 1
fi

if docker inspect -f '{{.State.OOMKilled}}' \
  memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1 | rg '^true$' >/dev/null; then
  echo "Refusing to start: a Memoria container reports OOMKilled=true." >&2
  exit 1
fi

docker inspect -f '{{.Name}}|running={{.State.Running}}|oom={{.State.OOMKilled}}' \
  memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1
docker stats --no-stream \
  --format '{{.Name}}|{{.MemUsage}}|{{.MemPerc}}|{{.CPUPerc}}' \
  memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1
memory_pressure | rg 'System-wide memory free percentage'

monitor_resources() {
  while true; do
    date -u '+%Y-%m-%dT%H:%M:%SZ'
    docker stats --no-stream \
      --format '{{.Name}}|{{.MemUsage}}|{{.MemPerc}}|{{.CPUPerc}}' \
      memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1
    memory_pressure | rg 'System-wide memory free percentage'
    sleep 5
  done
}

monitor_resources > "${RUN_DIR}/resource-samples.log" 2>&1 &
MONITOR_PID=$!

stop_monitor() {
  kill "${MONITOR_PID}" 2>/dev/null || true
  wait "${MONITOR_PID}" 2>/dev/null || true
}
trap stop_monitor EXIT INT TERM

"${PYTHON}" memoria/scripts/longmemeval/retrieve.py \
  --run-dir "${RUN_DIR}" \
  --start-index 0 \
  --limit 500 \
  --workers 1 \
  --top-k 20 \
  --explain verbose \
  --timeout 60 \
  --max-retries 3

stop_monitor
trap - EXIT INT TERM

"${PYTHON}" memoria/scripts/longmemeval/evaluate_retrieval.py \
  --run-dir "${RUN_DIR}" \
  --min-first-pass-success 0.99 \
  --max-p95-ms 30000

curl -fsS --max-time 5 http://127.0.0.1:8100/health >/dev/null
docker inspect -f '{{.Name}}|running={{.State.Running}}|oom={{.State.OOMKilled}}' \
  memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1
docker stats --no-stream \
  --format '{{.Name}}|{{.MemUsage}}|{{.MemPerc}}|{{.CPUPerc}}' \
  memoria-longmemeval-api-1 memoria-longmemeval-matrixone-1
memory_pressure | rg 'System-wide memory free percentage'

echo "Formal Retrieval-only run finished."
echo "Report: ${RUN_DIR}/report.md"
echo "Metrics: ${RUN_DIR}/metrics.json"
echo "Snapshot: ${RUN_DIR}/retrieval.jsonl"
echo "Resources: ${RUN_DIR}/resource-samples.log"
