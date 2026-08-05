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

The current run downloaded all core ARM64 images and successfully started the
full Compose stack once. The containers are currently stopped to keep the
competitor stacks serial; volumes remain available. The remaining blocker is
local account/app/API-key and model-provider initialization, not image
availability.
