# MOI RAG platform: benchmark-scope evidence note

**Date:** 2026-07-29  
**Evidence policy:** First-party MatrixOrigin product pages and MatrixOne Intelligence documentation only.

## Identity and scope decision

The repository itself does not expand “MOI” or link it to a vendor. The strongest official disambiguation is MatrixOrigin’s integration guide, which explicitly calls the service “MatrixOne Intelligence (MOI)’s RAG service.” MatrixOrigin separately documents **MatrixOne Intelligence** and the underlying **MatrixOne** database: MOI is the broader Data + AI product built on MatrixOne, not merely MatrixOne’s vector-search feature and not a standalone language model. Sources: [product introduction](https://docs.matrixorigin.cn/docs/moi4.0/en/overview/matrixone-intelligence-introduction.html), [MOI–DeerFlow guide](https://docs.matrixorigin.cn/docs/moi4.0/en/develop/deerflow.html), [official product page](https://www.matrixorigin.io/moi).

**Decision:** benchmark MatrixOne Intelligence as a product. Before execution, the benchmark owner should confirm that this is the intended “MOI” target and record the tested deployment, frontend/backend build versions, tenant/region, entitlements, and date.

## Product architecture and capabilities

Official documentation describes three layers:

1. A database and AI-service foundation for structured, semi-structured, unstructured, and vector data, plus LLM, embedding, vision, and speech services.
2. Data integration/governance that ingests, parses, cleans, enriches, chunks, and vectorizes multimodal inputs through visual workflows.
3. Data services that expose retrieval and application functions, including hybrid/multi-channel recall, search, Q&A, agents, APIs, and integrations.

The documented workflow surface exposes source/target locations, single/scheduled/load-triggered execution, priorities, branches, retries, and nodes for document/image/audio/video parsing, chunking, embedding, cleaning, extraction, and augmentation. Document parsing includes text, images, tables, and headings; OCR and image captioning are explicit stages; chunk length/overlap are configurable; the documented embedding node uses BAAI/bge-m3. Sources: [architecture](https://docs.matrixorigin.cn/docs/moi4.0/en/overview/matrixone-intelligence-introduction.html), [workflow](https://docs.matrixorigin.cn/docs/moi4.0/en/genai-workspace/data/processing/workflow.html).

The native answer surface is **Data Exploration (Explore)**: users select files/tables, ask cross-file questions, receive summaries/answers, and continue multi-turn conversations. Only files that completed embedding participate; disabled chunks are excluded. Selecting tables can invoke NL2SQL. The June 2026 notes describe a new RAG Agent Runtime with tool calls, evidence citation, RAG file retrieval, SQL tools, file-scope control, keyword retrieval, and source-binding fixes. Sources: [Data Exploration](https://docs.matrixorigin.cn/docs/moi4.0/en/genai-workspace/management/data_mgt/data_explore.html), [2026 release notes](https://docs.matrixorigin.cn/docs/moi4.0/en/release-notes/2026.html).

## User workflows and observable system boundaries

| Workflow | Boundary relevant to benchmarking |
|---|---|
| **Native MOI** | Load raw files → run parsing/chunking/embedding workflow → inspect jobs/artifacts → select embedded files in Explore → retrieve and answer. This is the appropriate native end-to-end benchmark path. |
| **MOI preparation + Dify** | The “Multimodal Document RAG Data Preparation” template creates processed knowledge data, then its guide exports that data to Dify and builds the application there. Dify generation/retrieval is outside MOI’s native boundary. |
| **MOI RAG service + DeerFlow** | MOI supplies processed-file listing/retrieval through an API; DeerFlow supplies the application, tool-calling base LLM, and chat UI. This is an integration benchmark, not the native-product run. |

Sources: [RAG preparation template](https://docs.matrixorigin.cn/docs/moi4.0/en/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html), [MOI–DeerFlow guide](https://docs.matrixorigin.cn/docs/moi4.0/en/develop/deerflow.html).

Observable outputs extend well beyond final text: task/job status and retry behavior, workflow configuration and topology, parsed JSON/Markdown, extracted images/tables, embedding JSON, previews/downloads, file/chunk eligibility, selected-file scope, retrieved evidence/citations, response text, and latency. PDF parsing supports source-text mapping in the Data Center, which is especially useful for the current PDF corpus. Sources: [Data Center](https://docs.matrixorigin.cn/docs/moi4.0/en/genai-workspace/management/data_mgt/catalog.html), [workflow operations](https://docs.matrixorigin.cn/docs/moi4.0/en/genai-workspace/data/processing/operation.html).

## Benchmark implications

This cannot be reduced to “which model answers best.” The measured treatment is the composed product: ingestion reliability, parser/OCR/layout fidelity, chunking, indexing, scope enforcement, retrieval, evidence binding, generation, workflow ergonomics, observability, and operating performance. Model-dependent answer quality remains one dimension, not the benchmark definition.

### Recommended core dimensions

- **Setup and reproducibility:** build/version, deployment mode, enabled models, workflow export/configuration, defaults versus permitted tuning, corpus checksum, reset procedure.
- **Ingestion and readiness:** accepted-file rate, failure reasons, retry recovery, duplicate/idempotent behavior, ingest-to-searchable time, and indexed-file/chunk coverage.
- **Parsing fidelity:** reading order, headings/hierarchy, tables, formulas, OCR, captions, page/source mapping, omissions, duplication, and artifact integrity.
- **Retrieval quality and isolation:** recall/ranking on answer-bearing passages, multi-file questions, distractors, exact selected-file scope, disabled-chunk exclusion, and evidence-to-source correctness.
- **Answer quality:** correctness, completeness, groundedness, citation precision/coverage, abstention for unanswerable questions, and multi-turn scope retention.
- **Performance and reliability:** median/tail ingestion and query latency, timeout/error rate, rerun consistency, cold/warm behavior, and any observable consumption/cost.
- **Product operability:** time/actions to build and run the native path, configuration clarity, progress/status accuracy, diagnostics, retry, lineage, preview, and exportability. Report these separately from answer-quality scores.

Use the same raw PDFs and a frozen native workflow policy across products. Preserve both end-to-end results and stage-level evidence; otherwise parsing or indexing failures will be misattributed to the generator.

### Defer or isolate into separate tracks

- Dify/DeerFlow/LangChain/MCP integrations and externally supplied LLMs.
- Agent actions, custom operators, NL2SQL/structured-table fusion, and knowledge-graph behavior.
- Non-PDF audio/video/image-only coverage, despite being product capabilities.
- RBAC/multi-tenant leakage, security/poisoning, governance, and audit evaluation.
- Dynamic-update freshness, high concurrency, elasticity, HA, and cost-at-scale.
- Controlled-generation/model-swap experiments; useful diagnostically, but not a substitute for the native product result.

## Material unknowns to resolve before freeze

- Whether the repository’s “MOI” definitively means MatrixOne Intelligence.
- Exact native Explore API/UI contract and how to export retrieved chunks, scores, citations, token usage, and timing reproducibly.
- Effective parser, embedding, reranker, retrieval, prompt, and generation-model versions in the tested deployment; documentation does not expose every runtime choice.
- Whether hybrid/keyword/vector retrieval and top-k/threshold/reranking are fixed, configurable, or tenant-specific.
- Feature availability differences between cloud and private deployments, plus quotas and pricing.
- Whether native Explore can be fully automated with supported APIs; the published workflow APIs and current UI documentation do not by themselves establish a stable benchmark harness.
