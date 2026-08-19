# FastGPT DocBench checkpoint — 2026-08-13 12:18 CST

## Resume target

- Run ID: `20260813-fastgpt-docbench-controlled-full-v2`
- Run directory: `runs/stage1/docbench-fastgpt/20260813-fastgpt-docbench-controlled-full-v2`
- Frozen package: `.local-services/competitor-eval-ready/v1/docbench/controlled-parsed-text`
- Evaluation condition: `CONTROLLED_PARSED_TEXT`
- Dataset revision: `local-frozen-v1`
- Planned resources/questions: 229 / 1102
- Parser input: reused controlled parsed-text artifacts for all 229 documents
- Embedding: `maas/bge-m3`, dimension 1024
- Generator: `qianfan/deepseek-v4-flash`
- FastGPT ingest split ceiling: `FASTGPT_PUSH_CHUNK_MAX_CHARS=4000`
- Main FastGPT vector workers: `VECTOR_MAX_PROCESS=16`
- Runner settings at pause: ingest concurrency 4, retrieval concurrency 16, QA concurrency 12

## Durable state at pause

The runner and FastGPT compute containers were stopped. MongoDB, PostgreSQL and Redis remain running; Docker volumes and all run artifacts are preserved.

Resource-map state after every runner process had exited:

| State | Resources | With FastGPT dataset/upload |
|---|---:|---:|
| ready | 80 | 80 |
| indexing | 2 | 2 |
| starting | 5 | 5 |
| failed | 136 | 18 |
| not_started | 6 | 0 |
| total | 229 | 105 |

The high `failed` count is not a final benchmark result. Several concurrent runners were still alive when the FastGPT app was intentionally stopped, so they recorded transport failures. A same-run resume must retry these resource states and retain/recheck the 105 already-created datasets instead of creating a new run.

- Retrieval ledger rows: 0
- QA ledger rows: 0
- Therefore no question-level result has been consumed and no metric denominator has been finalized.
- `resource-map.json` SHA-256: `23c3e47c704917b823b5b73ca587d6a1a1fe6c6ac7cbe2f78bc6910364ec6b1a`
- `resource-map.json.sha256`: matched at pause
- `start-record.json` SHA-256: `857f9b8283cc8df61e67c5c86ca129a845c4ec082fb0804977e21a20b519d4b7`
- `start-record.json.sha256`: matched at pause

Frozen input hashes from `start-record.json`:

- manifest: `9e63a636b5b261110f6380ae101a39923af0274652dde932a5d98180c7916f23`
- documents: `be24ac0151f0bd160bd06c0dc688fb5bdaa9440bea459569d0e3af64282a9558`
- questions: `72401d1c5828010a3de198281d076597d1df863173f8b0188273c1fa18262c02`
- gold: `27788d9a6d6cd8952d32ea44c66b2ef9695394765e877aeaef1161b1e1550e90`

## Stopped and preserved

- Stopped: all `competitor_eval_runner.py ... fastgpt_local ... 20260813-fastgpt-docbench-controlled-full-v2` processes.
- Stopped: `fastgpt-app`.
- Stopped: experimental `fastgpt-worker`; it did not materially consume vector tasks and should remain off until its queue behavior is adjusted.
- Preserved/running: `fastgpt-mongo`, `fastgpt-pg`, `fastgpt-redis` and the remaining support services.
- Preserved: all FastGPT datasets, vector-store contents, Mongo training state and run artifacts.
- The temporary `NON_EVAL` worker-trigger resources are excluded from the benchmark resource map and metrics.

## Safe same-run restart

1. Start only the main compute container first:

   ```bash
   docker start fastgpt-app
   ```

2. Wait until the app is healthy/reachable, then allow an additional 30 seconds for internal model and change-stream initialization. Do not start the experimental `fastgpt-worker` unless its queue consumption has first been fixed.

3. Ensure the Qianfan variables from `.local-services/providers/qianfan.env`, MaaS credentials, and `FASTGPT_PUSH_CHUNK_MAX_CHARS=4000` are present in the runner environment. Resume the exact same run ID:

   ```bash
   python3 local-rag-platforms/scripts/evaluation/competitor_eval_runner.py all \
     --system fastgpt_local \
     --package .local-services/competitor-eval-ready/v1/docbench/controlled-parsed-text \
     --output-root runs/stage1/docbench-fastgpt \
     --run-id 20260813-fastgpt-docbench-controlled-full-v2 \
     --fastgpt-ingest-concurrency 4 \
     --qa-concurrency 12 \
     --retrieval-concurrency 16 \
     --top-k 10 \
     --poll-seconds 2 \
     --index-timeout 600 \
     --query-timeout 180 \
     --qa-timeout 240
   ```

4. Run exactly one runner process. On restart, verify that `resource-map.json` remains hash-valid and that the 105 existing dataset IDs are reused. Do not manually rewrite `failed` states; the runner's same-run recovery path should replace transient transport failures after rechecking FastGPT.

5. Only after all 229 resources reach a terminal searchable state should retrieval and QA proceed. Metrics and `TODO.md` must not be updated before the terminal ledgers and denominator audit are complete.

## Known adjustment point

The previous attempt to add a second FastGPT app container did not increase vector-task consumption. The main container with `VECTOR_MAX_PROCESS=16` was the effective worker. Before restarting, the useful tuning target is FastGPT's internal Mongo/change-stream queue ownership, not additional runner processes. Multiple runners against the same run ID are forbidden because they race on the resource map even though each write is atomic.
