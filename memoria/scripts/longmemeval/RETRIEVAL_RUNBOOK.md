# LongMemEval-S Retrieval-only runbook

## 10-question Smoke

The frozen Smoke snapshot is under:

`memoria/runs/archive/longmemeval/longmemeval-s-bge-m3-relative-shift-v1-retrieval-top20-smoke10-v1`

Acceptance result on 2026-08-05: PASS.

- 10/10 final and first-pass successes
- 10/10 complete Top-20 responses
- zero cross-user or cross-question results
- zero missing provenance fields
- P50/P95 client latency: 344.5/627.2 ms
- retrieval path: 10/10 hybrid
- non-Abstention Recall@10: 0.8889
- non-Abstention Recall@20: 1.0000

## Historical stability stage

The accepted 100-question stability-stage output remains under `memoria/runs/`.
Its standalone runner was moved to
`memoria/scripts/archive/longmemeval/run_retrieval_100.sh` because it is not
required to reproduce the four final reported experiments.

## Run the formal 500-question experiment

For a clean formal-run resource baseline, use the recommended command:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/longmemeval/run_retrieval_500.sh --restart-services
```

`--restart-services` restarts only the dedicated `memoria-longmemeval` Compose
services. It preserves MatrixOne data and waits for the Memoria health endpoint
before retrieval starts. Omit the option when a service restart is not wanted:

```bash
./memoria/scripts/longmemeval/run_retrieval_500.sh
```

The frozen formal run directory is:

`memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/retrieval/top20-full500-v1`

The script is resumable. Re-running the identical command skips successful,
validated questions and retries only unfinished or failed questions. Do not
change Top-K, query construction, filters, concurrency, or run directory during
the formal run.

After completion, inspect:

```bash
RUN_DIR=/Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark/memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/retrieval/top20-full500-v1
cat "$RUN_DIR/report.md"
cat "$RUN_DIR/resource-samples.log"
wc -l "$RUN_DIR/retrieval.jsonl" "$RUN_DIR/checkpoint.jsonl" "$RUN_DIR/errors.jsonl"
```

Formal acceptance requires the same program and resource stability gates as the
100-question stage, with `500/500` replacing `100/100`. Evidence metrics use
470 non-Abstention questions; the 30 `_abs` questions are reported separately.

## Main artifacts

- `retrieval.jsonl`: immutable raw Top-20 snapshot plus normalized provenance
- `checkpoint.jsonl`: per-question completion log
- `errors.jsonl`: failed or validation-invalid final records
- `summary.json`: runner completion summary
- `metrics.json`: operational, evidence, category and Abstention metrics
- `report.md`: concise human-readable result and stability gate
- `resource-samples.log`: five-second API/MatrixOne/system memory samples
