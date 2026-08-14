# External model providers for local RAG platforms

The local services remain self-hosted, while model requests may use multiple
external providers. Provider credentials are platform-local and must never be
committed. TaaS remains configured; Baidu Qianfan V2 is added as an independent
fallback, not as a transparent retry behind the same model ID.

## Baidu Qianfan V2

Shared OpenAI-compatible values:

```dotenv
QIANFAN_BASE_URL=https://qianfan.baidubce.com/v2
QIANFAN_API_KEY=<local-secret>
QIANFAN_LLM_MODEL=deepseek-v4-flash
QIANFAN_EMBEDDING_MODEL=qwen3-embedding-8b
QIANFAN_EMBEDDING_DIMENSION=4096
QIANFAN_RERANKER_MODEL=qwen3-reranker-8b
QIANFAN_APPID=
```

Copy `qianfan.env.example` into the ignored runtime configuration for each
platform. The API key is a Qianfan ModelBuilder V2 API Key, not a BCE AK/SK
pair. The user-supplied API guide describes general BCE AK/SK request signing;
Qianfan's OpenAI-compatible inference path uses a Bearer API Key instead.

`QIANFAN_APPID` is optional and is not a secret. It identifies a Qianfan
application for usage/billing attribution and for API keys restricted to a
specific AppID. Leave it empty when the key permits all application identities.

The three requested model strings are candidate endpoint IDs. Confirm them
against `GET /v2/models` for the actual account before marking the provider
ready. Qianfan rerank uses `POST /v2/rerank` rather than an OpenAI Chat path.

Probe credentials before changing a platform:

```bash
set -a
source .local-services/providers/qianfan.env
set +a
python3 local-rag-platforms/providers/qianfan_probe.py --execute
```

## Platform mapping

| Platform | Qianfan registration path |
|---|---|
| MOI | Use `config.qianfan.example.json`; set `QIANFAN_API_KEY`; ingest into its separate database/table. The current pipeline has no reranker execution node yet. |
| Dify | Use compatible model providers for chat/embedding and register rerank separately against `/v2/rerank`. |
| FastGPT | Start the stack, then run `fastgpt_local.py provider --provider qianfan --execute`. |
| MaxKB | Add separate LLM, vector and rerank models; leave custom dimensions empty unless the UI requires 4096. |
| RAGFlow | After the resource gate is cleared, add and test Qianfan chat, embedding and rerank separately. |

Changing an embedding model changes the vector space. Never point an existing
TaaS/BGE-M3 corpus at Qianfan embeddings. Create a new knowledge base or vector
table and re-index the corpus; record provider, model ID and dimension in every
benchmark condition.
