# Local RAG competitor deployments

This directory contains the checked-in launcher, pinned version manifest,
sanitized configuration guidance, and the three-document smoke fixture. The
vendor checkouts, compose files, volumes, logs, API keys, and raw smoke
responses belong under the ignored `.local-services/` directory.

External model providers are independent from the self-hosted services.
MatrixOrigin TaaS remains available; Baidu Qianfan V2 is added as a separate
OpenAI-compatible fallback. Shared templates, probe tooling and re-index rules
are in `local-rag-platforms/providers/`.

The current host is macOS/Apple Silicon with Colima `linux/arm64` and 16 GiB
memory. Competitor services must run on this host. MatrixOrigin TaaS may be
used by the service as an external OpenAI-compatible LLM/Embedding provider;
the smoke result always records `model_egress=external`.

## Host preflight

```bash
python3 local-rag-platforms/prepare_local_services.py preflight
docker version
docker compose version
docker info
```

Run competitors serially. Keep the existing MOI containers on ports 8080,
6001, and 9876. The reserved competitor ports are:

| system | port | pinned source |
| --- | ---: | --- |
| `dify_local` | 8010 | Dify `1.16.1` (`8000` was occupied by an unrelated host process) |
| `fastgpt_local` | 3000 | FastGPT `v4.15.6` |
| `ragflow_local` | 9380 | RAGFlow `v0.26.4` |
| `maxkb_local` | 8090 | MaxKB `v2.10.4-lts` |

The exact source commit and image digests are recorded only after preparation
and image inspection:

```bash
python3 local-rag-platforms/prepare_local_services.py prepare dify_local
python3 local-rag-platforms/prepare_local_services.py record dify_local
```

Repeat those commands for the other systems. `prepare` does not copy vendor
source into the repository and does not create credentials.

## Smoke command

Install the existing evaluator package in editable mode, then run one platform
at a time. The command exits after writing a result even when a platform is
blocked, so a blocked local deployment is still auditable.

```bash
python3 -m pip install -e dify-rag-eval
python3 -m dify_rag_eval local-smoke \
  --system fastgpt_local \
  --base-url http://127.0.0.1:3000 \
  --api-key-env FASTGPT_API_KEY \
  --output .local-services/fastgpt_local/logs/smoke \
  --source local-rag-platforms/fixtures/smoke
```

The output contains a unified `smoke-result.json`, operation-level redacted
request/response artifacts, and a `.sha256` sidecar for every artifact. File
contents are represented by filename, size, and SHA-256; credentials are
redacted before persistence.

## Shared external model configuration

The service-specific UI or provider configuration must point to the existing
MatrixOrigin OpenAI-compatible endpoint. Use the project’s existing TaaS
environment values; do not commit the value of `TAAS_API_KEY`.

```dotenv
TAAS_BASE_URL=https://api-taas.moi.matrixorigin.cn/v1
TAAS_API_KEY=<existing-secret>
TAAS_CHAT_MODEL=<existing-chat-model>
TAAS_EMBEDDING_MODEL=BAAI/bge-m3
```

The official products normally persist model/provider configuration in their
own database or UI. A local `.env` change alone is not evidence that both
ingest and native QA use the local service; the smoke must probe both paths.

## Platform instructions

- [Dify local](dify_local/README.md)
- [FastGPT local](fastgpt_local/README.md)
- [RAGFlow local](ragflow_local/README.md)
- [MaxKB local](maxkb_local/README.md)

Official flow references are collected in
`plans/research/local-rag-official-flow-evidence-2026-08-05.md`; the final
cross-platform comparison is
`reports/local-rag-platform-comparison-2026-08-05.md`.
