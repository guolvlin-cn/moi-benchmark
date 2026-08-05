# RAGFlow local

Pinned source: RAGFlow `v0.26.4` from
<https://github.com/infiniflow/ragflow>. The official repository currently
documents prebuilt Docker images primarily for x86; verify the release image
manifest before attempting to pull it.

## Architecture gate

```bash
python3 local-rag-platforms/prepare_local_services.py prepare ragflow_local
docker buildx imagetools inspect infiniflow/ragflow:v0.26.4
```

If no ARM64 image is available, try the pinned official compose with the
current Colima amd64 emulation. Do not move the deployment to a remote host.
If it cannot start reliably or exhausts the 16 GiB host, write
`BLOCKED_LOCAL_ARCH` or `BLOCKED_LOCAL_RESOURCES` to the smoke result and keep
the logs and image manifest.

The v0.26.4 RAGFlow image and the configured CPU/Elasticsearch Compose
dependencies are now downloaded locally. The main RAGFlow, Elasticsearch,
MinIO, Valkey, sandbox executor, and TEI images use amd64 emulation; the
MySQL dependency uses the native arm64 image. No RAGFlow service has been
started yet.

RAGFlow’s local parser/DeepDoc/OCR/index pipeline must be kept separate in the
record. A parse/OCR failure is not a retrieval miss. Use the official compose
configuration with its supported document engine and an external TaaS
Embedding/LLM provider.

## API smoke

The initial adapter targets the documented HTTP API:

- `POST /api/v1/datasets/{dataset_id}/documents`
- `POST /api/v1/datasets/{dataset_id}/chunks`
- `GET /api/v1/datasets/{dataset_id}/documents`
- `POST /api/v1/retrieval`
- `POST /api/v1/openai/{chat_id}/chat/completions` with `extra_body.reference=true`

Create the chat assistant in the local UI and provide its local ID:

```bash
RAGFLOW_CHAT_ID=<local-chat-id> \
python3 -m dify_rag_eval local-smoke \
  --system ragflow_local \
  --api-key-env RAGFLOW_API_KEY \
  --chat-id "$RAGFLOW_CHAT_ID" \
  --output .local-services/ragflow_local/logs/smoke
```

The result records parser status, document status, retrieval contexts, and
native references as separate raw operations.
