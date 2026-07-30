# RAGBench → MOI throwaway prototype

Problem/assumption: validate Parquet → controlled PDF → MOI atomic processing/retrieval → diagnostic score. `response` and RAGBench labels are never Gold; evidence is explicitly unreviewed.

## Environment

The project pins Python 3.12 in `.python-version` and locks all runtime dependencies in `uv.lock`.

```bash
uv sync --frozen
uv run ragbench-moi --help
```

`uv sync --frozen` creates the local `.venv` without changing the lockfile. Activating it is optional; use `source .venv/bin/activate` when direct `python` and `ragbench-moi` commands are more convenient.

Run offline:

```bash
uv run ragbench-moi demo-offline
```

This writes the gitignored `runs/offline-smoke/`, including `state.json` and `feasibility.json`. It verifies Parquet→PDF→pypdf extraction→deterministic evidence retrieval→score. PDF verification compares every rendered nonblank body segment exactly, including spaces; source line breaks may be reflowed for page layout, and blank-line count is recorded separately. The manifest also records the input Parquet and generator hashes, so use a fresh run rather than treating generated artifacts as a checked-in fixture. The feasibility result is deliberately `PARTIAL/BLOCKED_CONTRACT`: processing and BYOA retrieval have no public dataset/document ID mapping or ingestion contract; Native Explore answer API is unconfirmed. Use the UI/workflow and `manual_explore_run.jsonl` for final response/citations.

MOI commands require `MOI_API_URL` and (for processing/poll/query) `MOI_API_KEY`. Probe is read-only `GET /byoa/api/v1/datasets`; without a key it reports `UNAUTHENTICATED_REACHABILITY`. Processing upload requires `--confirm-upload --acknowledge-license-review --expected-host HOST`; the host must exactly match `MOI_API_URL`. It sends only `moi-key`, multipart `files` plus JSON `payload` with ParseNode→ChunkNode→EmbedNode. Redirects are blocked. Query requires explicit `--dataset-id`; optional `--document-id` can be repeated. Local hashes are provenance only, never MOI IDs.

TechQA is third-party data for internal feasibility validation only. Before publishing or forwarding PDFs/results, perform a separate rights/license review (`license_status=UNREVIEWED_THIRD_PARTY`, `redistribution_allowed=UNKNOWN`).

`poll` records sanitized `job_status` and file mappings (`file_id`, `file_name`, `file_status`, `error_message`). The public contract does not document a `file_id` → retrieval dataset ID mapping; do not treat file IDs as dataset IDs. An authenticated probe may list dataset IDs/names, but each must be manually checked before query.

Official references: [MatrixOne atomic workflow API](https://docs.matrixorigin.cn/zh/m1intelligence/MatrixOne-Intelligence/workflow%20api/automic_api/), [DeerFlow GitHub](https://github.com/bytedance/deer-flow).

From this prototype directory, command templates are:

```bash
export MOI_API_URL=https://freetier-01.cn-hangzhou.cluster.matrixonecloud.cn
export MOI_API_KEY='...'
uv run ragbench-moi probe --run runs/probe --expected-host freetier-01.cn-hangzhou.cluster.matrixonecloud.cn
uv run ragbench-moi prepare --run runs/prepare
uv run ragbench-moi upload --run runs/prepare --confirm-upload --acknowledge-license-review --expected-host freetier-01.cn-hangzhou.cluster.matrixonecloud.cn
uv run ragbench-moi poll JOB_ID --run runs/prepare --expected-host freetier-01.cn-hangzhou.cluster.matrixonecloud.cn
uv run ragbench-moi query --run runs/prepare --expected-host freetier-01.cn-hangzhou.cluster.matrixonecloud.cn --dataset-id DATASET_ID --dataset-id ANOTHER_DATASET_ID
uv run ragbench-moi score --run runs/prepare
uv run ragbench-moi tui --run runs/prepare
```

Never paste a key into command arguments; credentials are read only from environment variables.
