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
and Embedding provider in the local instance, then verify both API paths:

```dotenv
DIFY_API_BASE_URL=http://127.0.0.1:8010/v1
DIFY_LOCAL_DATASET_API_KEY=<local-dataset-key>
DIFY_LOCAL_API_KEY=<local-app-key>
DIFY_EMBEDDING_MODEL=BAAI/bge-m3
DIFY_EMBEDDING_PROVIDER=<local-provider-name>
```

The existing evaluator uses `/datasets`,
`/datasets/{dataset_id}/document/create-by-file`,
`/datasets/{dataset_id}/documents`, `/datasets/{dataset_id}/retrieve`,
`/chat-messages`, and optionally `/workflows/run`. A local smoke only reports
a native answer as successful when that local app endpoint responds; it does
not infer local execution from the base URL alone.

```bash
python3 -m dify_rag_eval local-smoke \
  --system dify_local \
  --base-url http://127.0.0.1:8010/v1 \
  --output .local-services/dify_local/logs/smoke
```

## Resource and artifact rules

Dify is a multi-container stack. Start it only while the other competitor
stacks are stopped. After startup, record the source commit, compose image
list, image architecture, and repo digests:

```bash
python3 local-rag-platforms/prepare_local_services.py record dify_local
```
