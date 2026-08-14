# FastGPT local

Pinned source: FastGPT `v4.15.6` from
<https://github.com/labring/FastGPT>. The official self-host Docker flow is
documented at <https://doc.fastgpt.io/en/self-host/deploy/docker>.

## Prepare and start

```bash
python3 local-rag-platforms/prepare_local_services.py prepare fastgpt_local
```

Use the pinned release’s official PgVector compose variant under the prepared
checkout at
`document/public/deploy/docker/v4.15/global/docker-compose.pg.yml`. Keep the
FastGPT web port on `3000`; do not start it alongside a second competitor
stack. The pinned source checkout is `v4.15.6`, while the release’s checked-in
deployment file currently references FastGPT and code-sandbox images at
`v4.15.4`; this is recorded as a version divergence in the runtime manifest.
Configure at least one Language Model and one Index Model through the local UI.
Both may use the existing MatrixOrigin OpenAI-compatible TaaS endpoint, but
the product and its data services remain local.

```bash
docker compose -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml \
  up -d
curl -fsS http://127.0.0.1:3000
```

The runtime compose copy is based on the official file and supplies the local
values required by the current release (`FE_DOMAIN`, `FILE_DOMAIN`, and
`AGENT_ENGINE`). The source compose file remains unchanged under the pinned
checkout.

Create a local API key and a local app. The smoke adapter uses the documented
contracts:

- `POST /api/core/dataset/create`
- `POST /api/core/dataset/collection/create/localFile`
- `POST /api/core/dataset/searchTest`
- `POST /api/v1/chat/completions` with `detail=true`

```bash
python3 -m dify_rag_eval local-smoke \
  --system fastgpt_local \
  --api-key-env FASTGPT_API_KEY \
  --app-id-env FASTGPT_APP_ID \
  --output .local-services/fastgpt_local/logs/smoke
```

Use a new `chatId` for each question and repeat. Save `responseData` and
usage from the raw response; do not turn an answer string into a citation.
If an image manifest lacks ARM64 support, the only permitted fallback is the
current Colima amd64 emulation. Record the resulting platform as
`linux/amd64-emulated`.

The 2026-08-06 run completed provider initialization, root API model setup,
local API-key/app creation, and the three-document ingest/retrieval smoke. Both
`qwen3.6-flash` and `bge-m3` passed FastGPT model tests; all three collections
became ready and `searchTest` returned three hits. Native QA produced no HTTP
response after starting at `2026-08-06T03:44:03Z`, so the final result is
`partial`, with blocked reason
`NATIVE_QA_TIMEOUT_NO_RESPONSE_SINCE_2026-08-06T03:44:03Z`.

Evidence: `.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/`
(`smoke-result.json` SHA-256
`2e66b8fcbdf3da075fabd7ac8532e430f594749391872566f0039679cbb09a96`).
The Compose stack was stopped with `down`; named volumes were retained.

## Prepared local contract (do not start while another competitor is running)

Run the read-only verification at any time. It validates the pinned source,
expanded Compose, every recorded `linux/arm64` image manifest, and confirms no
FastGPT container is running. It does not pull images or mutate containers:

```bash
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py preflight
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py provider
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py smoke
```

The second command is also a dry run: it prints the versioned API contract in
`contracts.json`. The prepared smoke uses the v4.15.6 source contract, notably:

- local file upload sends a binary `file` plus a JSON-serialized multipart
  `data` field;
- readiness polls `collection/listV2` until all training counters are zero;
- `searchTest` sends `text` and reads matches from `data.list`;
- native QA sends `detail=true` and preserves `choices` and `responseData`.

Copy `.env.example` only into the ignored runtime directory. The populated file
must never be committed:

```bash
cp local-rag-platforms/fastgpt_local/.env.example \
  .local-services/fastgpt_local/fastgpt.env
chmod 600 .local-services/fastgpt_local/fastgpt.env
```

## Provider save failure diagnosis

The two authentication layers have different paths and must not be mixed:

- FastGPT v4.15.4/v4.15.6 UI: root browser session; create
  `POST /api/aiproxy/api/createChannel`, list
  `GET /api/aiproxy/api/channels/all`, and model test
  `GET /api/core/ai/model/test?model=...&channelId=...`.
- AIProxy v0.6.5 management API: `Authorization: Bearer <ADMIN_KEY>`;
  create `POST /api/channel/` (including the trailing slash), list
  `GET /api/channels/all`, and saved-channel test
  `GET /api/channel/{id}/test`.

`TAAS_API_KEY` belongs only in the channel payload's `key`; it does not
authenticate AIProxy management calls. The previous direct
`POST /api/createChannel` attempt therefore exercised no valid AIProxy route.
The v4.15.4 UI and v4.15.6 source contracts agree, so version drift is not the
cause. No backend create failure was observed from the UI attempt because no
request reached the handler.

After MaxKB has been stopped by its owner, execute exactly:

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
test -z "$(docker ps -q --filter name=maxkb)"
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py preflight
docker compose -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml up -d
for attempt in {1..90}; do
  curl -fsS http://127.0.0.1:3000 >/dev/null && break
  sleep 2
done
curl -fsS http://127.0.0.1:3000 >/dev/null
set -a
. .local-services/fastgpt_local/fastgpt.env
set +a
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py provider --execute
```

The provider verifier runs inside `fastgpt-app`, obtains the AIProxy admin key
from the running container without printing it, creates the channel only when
its name is absent, re-lists it, validates type/base URL/models, and tests all
saved models. It refuses to overwrite a mismatched or duplicate channel.

Sign in locally at `http://127.0.0.1:3000`. In **Account → Model Providers**,
confirm the new channel, import `taas-models.example.json` if those model
definitions are not already present, enable both models, and run each UI model
test. Create a local knowledge-base app wired to the smoke dataset, publish it,
and create a local API key. Record only its app ID and key in the ignored env file.

Add Qianfan as a second AIProxy channel without replacing TaaS:

```bash
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py \
  provider --provider qianfan --execute
```

The requested Qianfan condition uses `deepseek-v4-flash`,
`qwen3-embedding-8b` (4096 dimensions), and `qwen3-reranker-8b`. Treat these
strings as candidate endpoint IDs until `/v2/models` confirms the current
account exposes them. Create a new dataset; do not reuse a TaaS index.

Then run the prepared three-document contract:

```bash
set -a
. .local-services/fastgpt_local/fastgpt.env
set +a
python3 local-rag-platforms/fastgpt_local/fastgpt_local.py smoke --execute
```

This command refuses non-loopback FastGPT URLs. It creates a timestamped local
dataset, uploads the fixture documents, waits for indexing, runs direct
retrieval and native QA, and writes raw local evidence only below the ignored
`.local-services/fastgpt_local/logs/` directory.

Finally release the serial window while preserving all volumes:

```bash
docker compose -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml down
```
