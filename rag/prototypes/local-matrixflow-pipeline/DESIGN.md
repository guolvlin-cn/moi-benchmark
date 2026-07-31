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

The default profile represents the web `standard_rag` node
`moi:document.parse`, pinned to V2. Backends that cannot run locally are
explicit slots, never simulated:

| Route | Dependency | Local status |
| --- | --- | --- |
| PDF | MinerU | `not_configured` |
| PDF table preprocessing | Paddle | optional, `not_configured` |
| DOC/DOCX/PPT/PPTX | converter, then MinerU | `not_configured` |
| XLS/XLSX | OpenXML | `not_configured` |
| image OCR/caption | VLM | `not_configured` |

Text, Markdown, and HTML use MatrixFlow V3 Native only as an explicit
compatibility route because the web V2 legacy pre-dispatch implementation is
package-private. Its summary records `web_equivalent=false`.

### Stage 2 — index and knowledge QA

Input:

```text
documents.jsonl + embedding/chat configuration + MatrixOne
```

Ingestion:

```text
MatrixFlow SplitDocumentsLength(512, 50)
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
