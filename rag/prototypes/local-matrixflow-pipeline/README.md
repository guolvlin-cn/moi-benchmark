# Local MatrixFlow end-to-end pipeline

This throwaway orchestration prototype answers one question: can the two
standalone product stages be composed without deploying the MatrixFlow web
application?

```text
local-matrixflow-parser
  -> MatrixFlow documents.jsonl
  -> local-matrixflow-rag product SplitDocumentsLength (512/50)
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
  --input ../local-matrixflow-parser/data/sample.md \
  --config ../local-matrixflow-rag/config.local.json \
  --question "这个文档说明了什么？" \
  --run runs/e2e
```

Use `--dataset FILE.jsonl` instead of, or together with, `--question` for the
retrieval benchmark.

## Intentionally empty parser backends

The parser's `web-default` profile exposes the same V2 routing decision as the
web `standard_rag` template. These product-owned backends are not configured:

- **MinerU**: required for PDF layout/OCR and for Office documents after PDF
  conversion.
- **Paddle**: optional; only used when `enable_paddle_preprocess=true` for
  table-region detection and PDF whitening. The web default is `false`.
- **document converter**: required before MinerU for DOC/DOCX/PPT/PPTX.
- **OpenXML**: required for XLS/XLSX.
- **VLM**: required for standalone images and optional V2 enrichments.

Run the parser's dependency planner before a corpus run:

```sh
cd ../local-matrixflow-parser
go run ./cmd/local-matrixflow-parser plan --input /path/to/document.pdf
```

PDF and Office runs therefore stop with an explicit `not_configured` backend
error today. Markdown/plain/HTML use a clearly reported product V3 Native
compatibility route because the web V2 legacy pre-dispatch helper is not an
exported MatrixFlow package boundary.
