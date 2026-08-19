# MOI Stage 1 RAG benchmark

`moi_rag_benchmark.py` ingests the complete MOI-ready corpora for MMDocIR,
DocBench and MMDocRAG into three isolated MatrixOne tables, then runs the
planned Stage-1 question splits. The raw MOI response is retained in each
dataset's `query-run/<timestamp>/results.jsonl`.

The default run is the plan's first gate:

- MMDocIR: all 1,658 evaluation questions;
- DocBench: 20 PDFs / 50 questions smoke;
- MMDocRAG: a deterministic 200-question stratified sample from
  `evaluation_20.jsonl`.

Start it from a terminal, or double-click the executable `.command` file:

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
./scripts/benchmarks/start_moi_rag_benchmark.command
```

For the full DocBench question set:

```sh
./scripts/benchmarks/start_moi_rag_benchmark.command --full-docbench
```

To only build the selected isolated MOI/MatrixOne vector indexes and stop
before QA retrieval or LLM judging (for today's MMDocIR-only checkpoint, use
`--datasets mmdocir`):

```sh
./scripts/benchmarks/start_moi_rag_benchmark.command --ingest-only
./scripts/benchmarks/start_moi_rag_benchmark.command --ingest-only --datasets mmdocir
```

Ingestion batches MatrixOne row inserts (`insert_batch_size`, default 256) and
creates the IVFFLAT vector index after the data transaction commits. This keeps
large vector imports from paying the index-maintenance cost once per row.

The script loads `/Users/muuushroom/gitrepos/moi-benchmark/rag/.env` and the local
prototype `.env` without overwriting exported variables. TaaS embedding
requests use a bounded retry policy for transient gateway statuses (including
the observed 405 WAF response); 405 retries use a longer security-gateway
cooldown and the retry attempts are printed in the terminal. The local TaaS
import can set `embedding_batch_size` up to the endpoint's supported limit;
the importer still caps each request at 256 KiB of input text. Larger batches
reduce the chance of a long run being classified as high-frequency traffic.
TaaS embedding and generation requests bypass the process's
`HTTP_PROXY`/`HTTPS_PROXY` environment variables and connect directly; other
providers retain the default proxy behavior. During QA evaluation, generation
and DocBench Judge calls retry per question and can fail over to the configured
Baidu Qianfan V2 chat provider when `QIANFAN_API_KEY` is available. A question
that still fails is recorded as `failed`/`fail` and does not stop later
questions. Retrieval embedding failures are recorded as failed attempts; a
Qianfan embedding cannot transparently replace the BGE-M3 vectors in an
existing index because it is a different vector space. Corpus ingestion
errors remain hard stops. The run is marked `paused_api_error` for a
process-level API failure; `manifest.json`,
`state.json`, logs, completed raw responses and completed Judge rows remain under
`runs/stage1/moi-rag-native/<run_id>/`.

The paper-native MMDocIR page/layout metrics are explicitly recorded as N/A
when the MOI-ready MinerU Markdown blocks do not contain page-boundary/layout
trace. MMDocRAG image quote metrics are likewise N/A for the current native
`SearchRAGChunks` text path; adapted text retrieval, BLEU/ROUGE-L, and the
text-only Judge scores are kept separately and are not presented as strict
multimodal reproduction.
