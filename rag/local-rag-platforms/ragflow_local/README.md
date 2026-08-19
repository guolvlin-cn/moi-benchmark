# RAGFlow local

Pinned source: RAGFlow `v0.26.4` from
<https://github.com/infiniflow/ragflow>. The official repository currently
documents prebuilt Docker images primarily for x86; verify the release image
manifest before attempting to pull it.

## Architecture gate

```bash
python3 local-rag-platforms/scripts/deployment/prepare_local_services.py prepare ragflow_local
docker buildx imagetools inspect infiniflow/ragflow:v0.26.4
```

If no ARM64 image is available, try the pinned official compose with the
current Colima amd64 emulation. Do not move the deployment to a remote host.
If it cannot start reliably or exhausts the 16 GiB host, write
`BLOCKED_LOCAL_ARCH` or `BLOCKED_LOCAL_RESOURCES` to the smoke result and keep
the logs and image manifest.

The v0.26.4 RAGFlow image and the CPU/Elasticsearch dependencies are downloaded
locally. Registry inspection gives RAGFlow manifest digest
`sha256:16d24d1968ab59e2715a85d2590f1569c9539e0362344a42f3a23e8be06a655b`
and image-config digest
`sha256:3a1c37b9a815466dc2b3ca8bcbf47af26646fe64f59da3071cc060ee9036d2e0`.
The former is the pullable digest; an earlier image manifest mislabeled the
config digest as the manifest digest.

`compose.yaml` is a constrained `LOCAL_VARIANT` of the official v0.26.4
Elasticsearch/CPU compose. Only RAGFlow is pinned to `linux/amd64`; ES 8.11.3,
MySQL 8.0.39, MinIO, and Valkey select native arm64 manifests. TEI and sandbox
profiles are deliberately absent because MatrixOrigin TaaS supplies the
embedding/LLM APIs and the smoke does not execute code. ES is capped at 4 GiB
instead of the upstream 8,073,741,824-byte default; document and embedding
batches are reduced to 1 and 4. No RAGFlow service has been started yet.

## Resource and architecture decision

The pinned upstream README requires at least 4 CPU cores, 16 GB RAM, and 50 GB
disk. Current Colima is `linux/aarch64`, 2 CPUs, 12 GiB RAM, no swap, with 13
GiB free in `/var/lib/docker`. Its `qemu-x86_64` binfmt handler is enabled.
Therefore the current static gate is `BLOCKED_LOCAL_RESOURCES`, not
`BLOCKED_LOCAL_ARCH`.

- Use `BLOCKED_LOCAL_ARCH` only when x86_64 emulation is unavailable, or the
  RAGFlow container fails with `exec format error`, illegal instruction, or a
  repeatable emulator crash while memory/disk remain healthy.
- Use `BLOCKED_LOCAL_RESOURCES` when the official 4 CPU/16 GB/50 GB gate is not
  met, or trial evidence shows exit 137/OOM, ES allocation/read-only disk
  watermarks, `no space left`, or sustained health-check failure accompanied by
  memory/disk exhaustion.
- A parser/DeepDoc/OCR failure is an ingest failure, not a retrieval miss and
  not by itself an architecture/resource classification.

Run the read-only preflight (exit 42 means resources; exit 43 means arch):

```bash
local-rag-platforms/ragflow_local/preflight.sh
```

The preflight and `collect-evidence.sh` write only under
`.local-services/ragflow_local/logs/`. The collector never stops containers.

## Controlled trial after Dify is stopped

Do not run this while any `moi_dify_local-*` container is running. The exact
start command is:

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag && \
test -z "$(docker ps -q --filter name=moi_dify_local)" && \
docker compose --project-name moi_ragflow_local \
  --env-file .local-services/ragflow_local/compose/runtime.env \
  -f local-rag-platforms/ragflow_local/compose.yaml \
  up -d --no-build --pull never
```

Then collect evidence without stopping the stack:

```bash
local-rag-platforms/ragflow_local/collect-evidence.sh
```

## MatrixOrigin TaaS

After first local login, use **Model providers > OpenAI**, add the TaaS chat
and embedding model names, and set the OpenAI-compatible base URL (including
its `/v1` prefix) plus API key. Do not enable the local TEI profile. RAGFlow's
v0.26.4 documentation permits a provider API key and custom base URL; after a
user has logged in, provider changes must be made in the UI rather than
`service_conf.yaml.template`.

资源门槛解除并完成首次登录后，在 **Model providers > OpenAI** 中添加千帆：
Base URL `https://qianfan.baidubce.com/v2`，Chat 模型
`deepseek-v4-flash`，Embedding `qwen3-embedding-8b`（4096 维），Rerank
`qwen3-reranker-8b`。三种模型分别 probe，并为千帆创建独立 Dataset；模型
接入点 ID 以 `/v2/models` 为准。当前资源阻塞期间不标记为 ready。

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

All calls use `Authorization: Bearer <RAGFLOW_API_KEY>`. Upload is multipart
field `file`; parse requires JSON `document_ids`; readiness polling must keep
`UNSTART/RUNNING/DONE/FAIL` separate; retrieval requires `question` and either
`dataset_ids` or `document_ids`. For non-stream native QA, references are in
`choices[0].message.reference`.

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
