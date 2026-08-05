# Local BGE-M3 embedding service

This prototype exposes the official [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)
`BGEM3FlagModel` through an OpenAI-compatible HTTP API. It is intended for the
MOI/MatrixFlow local RAG benchmark, where the Go ingestion pipeline sends
`POST /v1/embeddings` requests and writes the returned dense vectors to the
MatrixOne `VECF64` column.

The service uses only BGE-M3's dense vectors. BGE-M3 also supports sparse and
ColBERT outputs, but those are not part of the current MOI vector-table
contract. The official model card documents a 1024-dimensional dense vector,
an 8192-token maximum length, and no need for a separate query instruction:
[BAAI/bge-m3 model card](https://huggingface.co/BAAI/bge-m3).

## API contract

The important endpoint is:

```text
POST http://127.0.0.1:8081/v1/embeddings
```

Request:

```json
{
  "model": "BAAI/bge-m3",
  "input": ["first document chunk", "second document chunk"],
  "encoding_format": "float"
}
```

Response shape is compatible with the existing Go client:

```json
{
  "object": "list",
  "data": [
    {"object": "embedding", "embedding": [0.01, 0.02], "index": 0}
  ],
  "model": "BAAI/bge-m3",
  "usage": {"prompt_tokens": 5, "total_tokens": 5}
}
```

The actual BGE-M3 vector contains 1024 floats. `usage` is an inexpensive
multilingual estimate and is informational; MOI does not use it for ingestion.
Both `/v1/embeddings` and `/embeddings` are accepted so the service works with
the current RAG adapter's `base_url + /embeddings` convention.

## Install from the official repository package

Do not install `sentence-transformers` as a substitute. This service depends
on the official `FlagEmbedding` package, which installs the model runtime and
its PyTorch/Transformers dependencies:

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-bge-m3-embedding
cp .env.example .env
uv sync
```

`uv sync` installs Python dependencies but does not download BGE-M3 weights.
With the default settings, the first embedding request downloads the model
from Hugging Face and stores it in the configured Hugging Face cache. This can
be a large download, so run it only when you are ready to use local BGE-M3.

If the model has already been downloaded or copied to a local snapshot, set:

```dotenv
BGE_MODEL_DIR=/absolute/path/to/the/BAAI--bge-m3-snapshot
BGE_LOCAL_FILES_ONLY=true
```

`BGE_MODEL_DIR` takes precedence over `BGE_MODEL`. `BGE_MODEL_ID` remains
`BAAI/bge-m3`, so the RAG client does not need to know the local filesystem
path. The first request can be slow while weights are downloaded; the RAG
configuration example uses a 600-second request timeout for that initial load.

## Start and check the service

The macOS launcher reads `.env`, starts Uvicorn on loopback, and leaves model
loading lazy by default:

```sh
./start_local_bge_m3.command
```

Or start it directly:

```sh
uv run --env-file .env uvicorn app:app --host 127.0.0.1 --port 8081
```

In another terminal:

```sh
curl -s http://127.0.0.1:8081/healthz
curl -s http://127.0.0.1:8081/v1/models
curl -s http://127.0.0.1:8081/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["MatrixFlow local RAG smoke test"]}'
```

`/healthz` reports `status: not_loaded` until the first request in lazy mode.
`/readyz` returns HTTP 503 until the model has loaded successfully. Set
`BGE_LAZY_LOAD=false` when startup should fail immediately if the model cannot
be loaded.

Device selection is controlled by `BGE_DEVICE=auto|cpu|mps|cuda`. `auto`
selects CUDA, then Apple MPS, then CPU. fp16 is enabled automatically only on
CUDA; leave `BGE_USE_FP16` empty on a Mac unless you have verified MPS support
for the installed PyTorch build. If MPS fails, set `BGE_DEVICE=cpu`.

## Connect the existing RAG ingestion pipeline

The Go adapter in `prototypes/local-matrixflow-rag` already understands the
OpenAI embedding response and does not require a code change. Copy the local
configuration example under a new name so the existing TaaS configuration is
preserved:

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag
cp config.local-bge-m3.example.json config.local-bge-m3.json
python3 local_matrixflow_rag.py check --config config.local-bge-m3.json
```

The relevant fields are:

```json
{
  "mode": "openai",
  "base_url": "http://127.0.0.1:8081/v1",
  "model": "BAAI/bge-m3",
  "api_key_env": "",
  "dimension": 1024
}
```

When `api_key_env` is empty, the Go client sends no `Authorization` header.
If you set `BGE_API_KEY` in the service `.env`, set a matching environment
variable in the RAG launcher's `.env` and change `api_key_env` to that variable
name. Keep the service bound to `127.0.0.1` unless you have explicitly secured
the network path.

Once `check` succeeds, use the same config for ingestion:

```sh
python3 local_matrixflow_rag.py ingest \
  --config config.local-bge-m3.json \
  --source data/documents \
  --run runs/local-bge-m3-001 \
  --force
```

The existing RAG splitter limits each request to at most 64 chunks and 256 KiB
of UTF-8 input, matching the service defaults. The model is called for both
document chunks and query text; BGE-M3's official retrieval guidance does not
require adding an instruction prefix to either side.

## Tests without model weights

The engine tests inject a fake model and therefore do not require PyTorch,
Hugging Face access, or model files:

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
