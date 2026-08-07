# Dify local

Pinned source: Dify Community Edition `1.16.1` from
<https://github.com/langgenius/dify>. The official Docker instructions are in
<https://github.com/langgenius/dify/blob/main/docker/README.md>.

## Prepare and start

```bash
python3 local-rag-platforms/prepare_local_services.py prepare dify_local
cd .local-services/dify_local/source/dify/docker
cp .env.example .env
```

Set the external provider values in this runtime-only `.env` as required by
the pinned release. The planned host port `8000` was already occupied by an
unrelated uvicorn process, so this run uses `8010` using the release’s
`EXPOSE_NGINX_PORT` setting, then initialize the local instance at
<http://127.0.0.1:8010/install>.

```bash
docker compose -p moi_dify_local up -d
docker compose -p moi_dify_local ps
curl -fsS http://127.0.0.1:8010/console/api/setup
```

Do not reuse Dify Cloud app keys or dataset IDs. Create a local admin, local
dataset API key, and local app API key. Configure the MatrixOrigin TaaS LLM
and Embedding provider in the local instance. This run packages and installs
the repository-owned `dify-plugins/matrixorigin-taas` provider through Dify's
local `.difypkg` mechanism. It exposes `deepseek-v4-flash` and `bge-m3`; local
package signature verification is disabled only for this private,
locally-built package (`FORCE_VERIFYING_SIGNATURE=false`). Then verify both API
paths:

```dotenv
DIFY_API_BASE_URL=http://127.0.0.1:8010/v1
DIFY_LOCAL_DATASET_API_KEY=<local-dataset-key>
DIFY_LOCAL_API_KEY=<local-app-key>
DIFY_LOCAL_DATASET_ID=<local-dataset-id>
DIFY_EMBEDDING_MODEL=bge-m3
DIFY_EMBEDDING_PROVIDER=matrixorigin/matrixorigin_taas/matrixorigin_taas
```

The existing evaluator uses `/datasets`,
`/datasets/{dataset_id}/document/create-by-file`,
`/datasets/{dataset_id}/documents`, `/datasets/{dataset_id}/retrieve`,
`/chat-messages`, and optionally `/workflows/run`. A local smoke only reports
a native answer as successful when that local app endpoint responds; it does
not infer local execution from the base URL alone.

## Baidu Qianfan fallback provider

Keep the MatrixOrigin provider. In the local Dify workspace, install or select
the OpenAI-compatible model provider and create separate Qianfan models:

```text
Base URL:   https://qianfan.baidubce.com/v2
API Key:    QIANFAN_API_KEY
Chat:       deepseek-v4-flash
Embedding:  qwen3-embedding-8b (4096 dimensions)
Reranker:   qwen3-reranker-8b
```

Test Chat and Text Embedding independently. Create a new Dify dataset for
Qianfan embeddings; never change the provider on an existing TaaS/BGE-M3
dataset. Register Rerank separately because it uses `/v2/rerank`, not an
OpenAI Chat endpoint. Model strings remain pending `/v2/models` confirmation.

```bash
python3 -m dify_rag_eval local-smoke \
  --system dify_local \
  --base-url http://127.0.0.1:8010/v1 \
  --output .local-services/dify_local/logs/smoke \
  --embedding-model bge-m3 \
  --embedding-provider matrixorigin/matrixorigin_taas/matrixorigin_taas
```

The completed 2026-08-06 smoke reused the app-linked dataset, indexed all
three fixture documents, returned five direct-retrieval contexts, and produced
a non-empty native answer. Its redacted evidence is under
`.local-services/dify_local/logs/smoke-2026-08-06/`.

The follow-up corpus readiness run created a separate local dataset and
uploaded all 44 prepared benchmark Markdown documents. All documents reached
the indexed/ready condition; retrieval and the local app endpoint also
responded successfully. Evidence is under
`.local-services/dify_local/logs/readiness-44docs-2026-08-06/`. This is an
index-readiness check, not a Stage 1 benchmark run.

## Resource and artifact rules

Dify is a multi-container stack. Start it only while the other competitor
stacks are stopped. After startup, record the source commit, compose image
list, image architecture, and repo digests:

```bash
python3 local-rag-platforms/prepare_local_services.py record dify_local
```
