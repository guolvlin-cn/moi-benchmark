#!/bin/zsh
set -u

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
cd "$ROOT" || exit 1

echo "MOI Stage-1 RAG benchmark"
echo "Run root: $ROOT/runs/stage1/moi-rag-native"
echo "API errors will pause the run and preserve the checkpoint."
echo

exec python3 "$ROOT/benchmarks/moi_rag_benchmark.py" "$@"
