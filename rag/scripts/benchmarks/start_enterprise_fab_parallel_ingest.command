#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RAG="$ROOT/prototypes/local-matrixflow-rag"
RUN_ROOT="$ROOT/runs/stage1/enterprise-fab-parallel"
BIN="$RUN_ROOT/local-matrixflow-rag"
ENTERPRISE_DOCS="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/enterpriserag-bench/moi-documents.jsonl"
FAB_DOCS="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/fab-bench-mineru/moi-documents.jsonl"
mkdir -p "$RUN_ROOT"

set -a
source "$ROOT/.env"
set +a
[[ -n "${MAAS_API_KEY:-}" ]] || { print -u2 "MAAS_API_KEY is missing"; exit 1; }
[[ -n "${MINERU_API_TOKEN:-}" ]] || { print -u2 "MINERU_API_TOKEN is missing"; exit 1; }
[[ -f "$ENTERPRISE_DOCS" ]] || { print -u2 "Enterprise MOI-ready corpus is missing"; exit 1; }

# Keep the two research providers off the host proxy. The MaaS Go transport is
# already direct; NO_PROXY also covers MinerU's HTTP client and wget downloads.
PROVIDER_NO_PROXY="mineru.net,api.modelarts-maas.com"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}$PROVIDER_NO_PROXY"
export no_proxy="${no_proxy:+$no_proxy,}$PROVIDER_NO_PROXY"

cd "$RAG"
go build -o "$BIN" .
cd "$ROOT"

(
  print "Enterprise: embedding -> MatrixOne -> L2 index"
  "$BIN" ingest --force \
    --config "$RAG/config.enterpriserag-bench.maas.json" \
    --documents "$ENTERPRISE_DOCS" \
    --run "$RUN_ROOT/enterprise-ingest"
) >"$RUN_ROOT/enterprise.log" 2>&1 &
ENTERPRISE_PID=$!
print "Enterprise branch pid=$ENTERPRISE_PID log=$RUN_ROOT/enterprise.log"

(
  print "FAB: MinerU precision (45 acquired PDFs; >200 pages split to 180) -> merge 82 evidence-only docs"
  python3 "$ROOT/benchmarks/prepare_fab_bench_mineru.py" --workers 3
  print "FAB: embedding -> MatrixOne -> L2 index"
  "$BIN" ingest --force \
    --config "$RAG/config.fab-bench.maas.json" \
    --documents "$FAB_DOCS" \
    --run "$RUN_ROOT/fab-ingest"
) >"$RUN_ROOT/fab.log" 2>&1 &
FAB_PID=$!
print "FAB branch pid=$FAB_PID log=$RUN_ROOT/fab.log"

print "$ENTERPRISE_PID" >"$RUN_ROOT/enterprise.pid"
print "$FAB_PID" >"$RUN_ROOT/fab.pid"
wait "$ENTERPRISE_PID"
wait "$FAB_PID"
print "EnterpriseRAG-Bench and FAB-Bench ingestion completed."
