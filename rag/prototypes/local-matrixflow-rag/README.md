# Local Matrixflow RAG benchmark smoke pipeline

This is a runnable pipeline smoke test for the local RAG service deployed in
`matrixflow/poc-hub/rag-local`. It is deliberately not the v0.4 formal pilot:
it does not create Golden claims, citations, PDF page provenance, or Judge
scores.

## Contract

The adapter calls only these public endpoints:

- `POST /ingest` with `{ "text": "..." }`
- `POST /chat` with `{ "message": "..." }`

Input documents are `.md` and `.txt`. They are parsed locally as UTF-8 text,
then recorded with path and SHA-256 in `ingest-state.json`. A repeat `ingest`
skips unchanged content; use `--force` to intentionally send every document
again. The current target service has no delete/upsert API, so forced ingestion
creates duplicate vectors by design.

## Start the local RAG target

From the Matrixflow checkout:

```sh
cd /Users/muuushroom/gitrepos/matrixflow/poc-hub/rag-local
python3 mock_ai.py

RAG_MODE=mock \
EMBEDDING_BASE_URL=http://127.0.0.1:8001 \
LLM_BASE_URL=http://127.0.0.1:8001 \
DB_PATH=/tmp/matrixflow-rag-local/rag.db \
python3 app.py
```

## Run the full smoke pipeline

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag
python3 local_matrixflow_rag.py pipeline \
  --source data/documents \
  --dataset data/questions.jsonl \
  --run runs/smoke-001 \
  --repeats 2
```

Artifacts:

```text
runs/smoke-001/
├── ingest-state.json  # parser/ingest state, hashes, service IDs and errors
├── results.jsonl      # one raw answer/source record per question × repeat
├── summary.json       # request success, answer/source keyword recall, mean/P95 latency
└── report.md          # short human-readable summary
```

Re-run only document ingestion or evaluation:

```sh
python3 local_matrixflow_rag.py ingest --source data/documents --run runs/smoke-001
python3 local_matrixflow_rag.py run --dataset data/questions.jsonl --run runs/smoke-001 --repeats 2
python3 local_matrixflow_rag.py report --run runs/smoke-001
```

The target URL defaults to `http://127.0.0.1:8000`; override it with
`--base-url` for another local deployment.

`answer_keyword_recall` and `source_keyword_recall` are intentionally separate:
the latter proves that the RAG target retrieved the expected document fact,
while the former exposes whether the configured generator actually used it.
