# Local MatrixFlow end-to-end pipeline

This throwaway orchestration prototype answers one question: can the two
standalone product stages be composed without deploying the MatrixFlow web
application?

```text
local-matrixflow-parser
  -> MatrixFlow documents.jsonl
  -> local-matrixflow-rag product SplitDocumentsLength (512/64)
  -> product MultiLevelIndex (doc/section/chunk, section_size=5)
  -> MatrixOne + embedding
  -> product FindRAGFiles/SearchRAGChunks
  -> the checked-out MatrixFlow Explore system prompt + tool loop
```

Every invocation allocates a new timestamped directory. Child parser, ingest,
question-answer, and benchmark runs also keep their own immutable run folders.

## Run

Start the MatrixOne container from `../local-matrixflow-rag`, configure its
embedding/chat endpoints, then run:

```sh
python3 pipeline.py \
  --input /absolute/path/document.pdf \
  --config ../local-matrixflow-rag/config.local.json \
  --parser-pipeline precision \
  --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
  --question "这个文档说明了什么？" \
  --run runs/e2e
```

Use `--dataset FILE.jsonl` instead of, or together with, `--question` for the
retrieval benchmark.

The pipeline keeps MatrixFlow's normal `OVERWRITE` behavior by default. Pass
`--force` only when intentionally rebuilding the local table (for example after
changing the embedding dimension).

## Parser pipelines

The orchestrator supports four explicit parser routes:

- `precision`: official MinerU V4 precision parsing; requires
  `MINERU_API_TOKEN` and returns rich ZIP/Markdown output.
- `agent`: official token-free Agent lightweight parsing; lower limits and
  Markdown-only output.
- `local`: the original MatrixFlow local parser route controlled by
  `--parser-profile web-default|v3-native`.
- `vlm`: TaaS VLM parsing normalized into the same MatrixFlow document format.

The shared environment file defaults to the repository RAG root and is loaded
without overriding explicitly exported variables. It supplies both
`MINERU_API_TOKEN` to parsing and `TAAS_API_KEY` to embedding/generation.

Inspect a route before a corpus run:

```sh
cd ../local-matrixflow-parser
go run ./cmd/local-matrixflow-parser plan \
  --input /path/to/document.pdf \
  --pipeline precision
```
