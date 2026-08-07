# Local MatrixFlow product RAG benchmark

This benchmark runs MatrixFlow's native
`moi-core/agent-tools/knowledge/service.NewSearchRAGChunks` implementation
locally. It does not call the old `poc-hub/rag-local` service and does not
reimplement retrieval in Python.

The local stack is intentionally small:

```text
benchmark CLI
  ├── MatrixFlow SearchRAGChunks
  ├── MatrixOne vector/full-text table
  └── embedding adapter
```

It does not require `moi-frontend`, `moi-backend`, Catalog, or a running
Worker. Ingestion executes MatrixFlow's `SplitDocumentsLength` and
`MultiLevelIndex` WorkItems, then reuses the production vector preparation,
table-schema/index, stable-ID, and upsert functions from
`moi:data.retrieval.vector.write`. All retrieval, candidate merging, ranking,
and evidence expansion are executed by the product RAG module.

The ingestion defaults match `rag-ingest-default-v1`: chunk size 512, overlap
64, five chunks per section. Embedding input truncation and batching are also
the production limits: UTF-8 8192 bytes per input, at most 64 inputs and 256
KiB per request. Vector upserts use the product writer's fixed 50-row batches.

## What this measures

Primary retrieval metrics:

- source recall and source recall@1/3/5/10;
- evidence substring recall;
- mean reciprocal rank;
- answerability accuracy for cases labeled `expected_answerable`;
- mean, P50, and P95 retrieval latency;
- embedding, schema inspection, full-text, vector, and evidence-expansion
  stage latency;
- raw routes, chunks, scores, and content for every attempt.

Optional controlled generation adds answer keyword recall and generation
latency. It uses the retrieved product chunks but deliberately does not claim
to reproduce the `explore` A2A Agent. This keeps Agent planning and browser
rendering outside the RAG benchmark.

## Repository layout requirement

The Go module imports the local MatrixFlow checkout through `replace`
directives. The default layout is:

```text
gitrepos/
├── matrixflow/
└── moi-benchmark/
    └── rag/prototypes/local-matrixflow-rag/
```

This makes the tested MatrixFlow source explicit: changing the sibling
`matrixflow` checkout changes the implementation under test.

## 1. Start only MatrixOne

Docker Compose uses the same MatrixOne image pinned by the MatrixFlow
repository:

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag
docker compose up -d
```

MatrixOne listens on `127.0.0.1:6001` with the default local credentials in
`config.example.json`.

## 2. Configure MatrixOrigin TaaS

Copy the example without committing local credentials:

```sh
cp config.example.json config.local.json
cp .env.example .env
```

The Python launcher automatically loads `.env` from this directory without
overriding an explicitly exported environment variable.

The default configuration uses MatrixOrigin Genesis TaaS:

- Base URL: `https://api-taas.moi.matrixorigin.cn/v1`
- embedding endpoint: `/embeddings`
- chat endpoint: `/chat/completions`
- authentication: `Authorization: Bearer $TAAS_API_KEY`

The example model IDs follow the
[TaaS documentation](https://taas.moi.matrixorigin.cn/taas/docs):
`BAAI/bge-m3` (the `rag-ingest-default-v1` workflow default) for embeddings
and `qwen3.6-flash` for optional generation. A key may restrict which models it can call, so replace either
model ID with one enabled for your key when necessary. Keep
`embedding.dimension` equal to the selected embedding model's output
dimension; changing the embedding model requires re-ingesting the corpus.

`mode: "taas"` fills in the TaaS Base URL and `TAAS_API_KEY` environment
variable when either field is omitted. The underlying request and response
format remains OpenAI-compatible.

Existing SiliconFlow or other OpenAI-compatible configurations remain
supported: keep `embedding.mode` as `"openai"` and retain their existing
`base_url`, model, and `api_key_env`. This migration changes the active example
configuration without deleting the previous provider path.

### Baidu Qianfan V2 fallback

`config.qianfan.example.json` uses Qianfan's OpenAI-compatible V2 endpoint,
`qwen3-embedding-8b` at 4096 dimensions, and batch size 16. Generation is
configured for the requested candidate ID `deepseek-v4-flash`. It uses a
separate MatrixOne database/table because Qianfan and TaaS/BGE-M3 vectors are
not interchangeable:

```sh
export QIANFAN_API_KEY='<local-secret>'
python3 local_matrixflow_rag.py check --config config.qianfan.example.json
```

Copy the example before a real run. Never repoint an existing TaaS index at
Qianfan.

For an offline wiring smoke test, use:

```json
{
  "mode": "hash",
  "model": "deterministic-hash-smoke",
  "dimension": 256
}
```

Hash mode is deterministic and useful for tests, but its quality numbers are
not representative of the MatrixFlow product model.

`config.offline.example.json` is a ready-to-copy hash-mode configuration for
an offline wiring smoke test.

## 3. Check dependencies

```sh
python3 local_matrixflow_rag.py check --config config.local.json
```

The check verifies the embedding adapter, MatrixOne connection, benchmark
database, and product-compatible vector table.

## 4. Run the complete benchmark

```sh
python3 local_matrixflow_rag.py pipeline \
  --config config.local.json \
  --source data/documents \
  --dataset data/questions.jsonl \
  --run runs/product-rag-001 \
  --max-hits 10 \
  --repeats 3 \
  --force
```

`--run` specifies an artifact root. Every `ingest`, `run`, or `pipeline`
invocation creates a new timestamped child directory and prints its exact
path, so a later execution never overwrites an earlier result.

Individual stages:

```sh
python3 local_matrixflow_rag.py ingest \
  --config config.local.json \
  --source data/documents \
  --run runs/product-rag-001 \
  --force

python3 local_matrixflow_rag.py run \
  --config config.local.json \
  --dataset data/questions.jsonl \
  --run runs/product-rag-001 \
  --max-hits 10 \
  --repeats 3
```

To ingest the standalone parser output:

```sh
python3 local_matrixflow_rag.py ingest \
  --config config.local.json \
  --documents /path/to/parser-run/documents.jsonl \
  --run runs/product-rag-001 \
  --force
```

To resume a batch-committed ingest without re-embedding the existing prefix,
pass the prior child run's progress file and omit `--force`:

```sh
python3 local_matrixflow_rag.py ingest \
  --config config.mmdocir.local-bge-m3.json \
  --documents /path/to/moi-documents.jsonl \
  --run runs/product-rag-001 \
  --resume-progress /path/to/prior-run/ingest-progress.json
```

Resume validates the parsed, expanded, embedded, committed, and database row
counts before making an embedding request. It starts after the prior
`batch_end`, keeps the existing rows, and rebuilds IVFFLAT only after the full
corpus is committed. `--resume-progress` and `--force` are mutually exclusive.

## Explore-compatible knowledge question

`ask` loads the checked-out MatrixFlow Knowledge Explore system prompt and
exposes the real `FindRAGFiles` and `SearchRAGChunks` implementations as model
tools:

```sh
python3 local_matrixflow_rag.py ask \
  --config config.local.json \
  --question "What does the document say about retrieval?" \
  --run runs/product-rag-001
```

This requires `generation.enabled=true` and an OpenAI-compatible chat endpoint
with tool-call support. It does not deploy the frontend or A2A transport; the
prompt, tool order, source-selection contract, ingestion transforms, and
retrieval implementations are taken from the checked-out product.

`--force` drops and recreates only the configured benchmark vector table, so
embedding-dimension changes are applied. Without it, the product
`OVERWRITE` policy deletes and rewrites only the IDs present in the current
batch; stale rows for removed source documents can remain, matching the
MatrixFlow workflow semantics.

The local embedding adapter still calls the configured OpenAI-compatible
endpoint directly because this benchmark has no running MatrixFlow workspace
Embedding API. To compare retrieval quality, use the same model/backend as
the product workflow; the local adapter shares the product's input shaping,
float32-to-float64 conversion, and vector-write contract. For long TaaS
imports, `embedding_batch_size` may be raised (the request is still capped at
256 KiB of input text) to avoid high-frequency gateway throttling; the default
64-input setting remains suitable for other providers.

### Local BGE-M3 embedding service

For a fully local embedding path, start
`../local-bge-m3-embedding/start_local_bge_m3.command`. That service wraps the
official FlagEmbedding `BGEM3FlagModel` and exposes the same OpenAI-compatible
`/v1/embeddings` contract, so no Go adapter change is required. Copy
`config.local-bge-m3.example.json` to a local config and run the normal
`check`/`ingest` commands with it:

```sh
cp config.local-bge-m3.example.json config.local-bge-m3.json
python3 local_matrixflow_rag.py check --config config.local-bge-m3.json
```

The local config uses `mode: "openai"`,
`base_url: "http://127.0.0.1:8081/v1"`, an empty `api_key_env`, and dimension
1024. Model weights are loaded on the first request by default; run the
service's `/readyz` check before a long import. The service README contains
the device, cache, offline-model, and optional local API-key settings.

## Dataset contract

Each JSONL row has this shape:

```json
{
  "id": "q-001",
  "question": "Which retrieval routes are combined?",
  "retrieval_keywords": ["full-text", "vector", "routes"],
  "relevant_documents": ["guide.md"],
  "relevant_evidence": ["full-text and vector routes"],
  "expected_answer_keywords": ["full-text", "vector"],
  "expected_answerable": true
}
```

`retrieval_keywords` are supplied directly to the same product tool interface
used by Agent Runtime. Curated keywords isolate retrieval quality from Agent
query planning. If omitted, the full question is used as one keyword.

Gold source identities are filenames and evidence text, not generated chunk
IDs. This keeps the dataset stable when chunking changes.

## Artifacts

```text
runs/product-rag-001/
└── 20260731-123456.789/
    ├── ingest-state.json  # source hashes, stable file/chunk IDs, offsets, model
    ├── results.jsonl      # raw product retrieval output and per-case metrics
    ├── summary.json       # aggregate quality and latency
    └── report.md          # human-readable summary
```

## Optional controlled generation

Set `generation.enabled=true`. With `generation.provider` set to `"taas"`, the
Base URL and API key environment variable default to the same TaaS values used
for embeddings. The generator receives only the chunks returned by MatrixFlow
RAG and is instructed to cite source filenames.

This mode measures a controlled retrieve-then-generate pipeline. Testing the
exact dev webpage experience remains a separate black-box A2A benchmark because
the product `explore` Agent adds planning, retries, source selection, and
session state beyond the RAG retriever.
