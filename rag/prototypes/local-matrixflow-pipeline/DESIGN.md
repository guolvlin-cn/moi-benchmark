# MatrixFlow local two-stage design

## Boundary

The local system has two independently testable stages and one orchestration
layer.

### Stage 1 — document parsing

Input:

```text
local file + file type + parser options
```

Output:

```text
documents.jsonl
result.json
summary.json
product artifacts
```

`documents.jsonl` is the stable boundary. Every row is a MatrixFlow document:

```json
{"id":"...","content":"...","type":"text","metadata":{"file_id":"...","file_name":"..."}}
```

The orchestration layer selects one explicit parser pipeline:

| Pipeline | Route | Authentication |
| --- | --- | --- |
| `precision` | official MinerU V4 | `MINERU_API_TOKEN` |
| `agent` | official MinerU Agent V1 | none |
| `local` | MatrixFlow V3 Native or V2 boundary | none for native formats |

Official MinerU output is normalized through MatrixFlow Markdown blocks. The
run records the provider, model, remote task IDs, stage timings, and download
transport. It remains marked `web_equivalent=false` because it is not the
MatrixFlow-pinned MinerU deployment.

### Stage 2 — index and knowledge QA

Input:

```text
documents.jsonl + embedding/chat configuration + MatrixOne
```

Ingestion:

```text
MatrixFlow SplitDocumentsLength(512, 64)
  -> MatrixFlow MultiLevelIndex(section_size=5)
  -> embedding
  -> product-compatible MatrixOne table
```

Online QA:

```text
checked-out Knowledge Explore system prompt
  -> FindRAGFiles
  -> SearchRAGChunks
       -> full-text route
       -> vector L2 route
       -> product candidate merge
       -> section/table evidence expansion
  -> validated select_final_sources
  -> final answer
```

Retrieval-only benchmark mode bypasses Agent keyword planning by consuming
curated `retrieval_keywords`. `ask` mode includes model planning and therefore
measures the local equivalent of the web knowledge-answer behavior.

### Orchestration

`pipeline.py` allocates one top-level immutable run directory, invokes Stage 1
for each input file, concatenates the document boundary, invokes Stage 2
ingestion, then optionally invokes `ask` and/or the retrieval dataset runner.

It contains no parsing, chunking, indexing, retrieval, or answering logic of
its own.

## Conformance rule

A run may only be called web-equivalent when every stage summary reports
`web_equivalent=true` and no dependency is `not_configured`. The Markdown
offline smoke path proves composition and retrieval wiring, not V2 parser
quality.
