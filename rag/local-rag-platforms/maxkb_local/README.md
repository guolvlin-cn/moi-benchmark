# MaxKB local

Pinned source reference: MaxKB `v2.10.4-lts` from
<https://github.com/1Panel-dev/maxkb>. The official Docker image defaults to
port `8080`; this project maps it to local port `8090` so the existing MOI
OpenXML parser remains untouched.

## Prepare and start

```bash
python3 local-rag-platforms/prepare_local_services.py prepare maxkb_local
docker run -d --name moi-maxkb-local \
  --platform linux/arm64 \
  -p 8090:8080 \
  -v "$PWD/.local-services/maxkb_local/data:/opt/maxkb" \
  1panel/maxkb:v2.10.4-lts
curl -fsS http://127.0.0.1:8090
```

If the image manifest does not provide ARM64, retry only with the current
Colima `linux/amd64` emulation and record that platform. Never use a remote
machine to turn a failed local deployment into a pass.

The pinned `1panel/maxkb:v2.10.4-lts` image has been downloaded locally as
`linux/arm64`. The container is not running yet; start it only when the MaxKB
smoke phase resumes.

Complete the local admin initialization and configure the MatrixOrigin TaaS
LLM/Embedding provider in the local UI. Create a local application API key.
MaxKB documents an OpenAI-compatible application endpoint, but the exact
instance path is deployment/API-document dependent. Discover the local
OpenAPI/Swagger document first and pass the endpoint explicitly:

```bash
export MAXKB_OPENAI_BASE_URL=http://127.0.0.1:8090/<local-app-openai-base>
export MAXKB_OPENAI_PATH=/chat/completions
export MAXKB_API_KEY=<local-app-key>
python3 -m dify_rag_eval local-smoke \
  --system maxkb_local \
  --api-key-env MAXKB_API_KEY \
  --native-base-url "$MAXKB_OPENAI_BASE_URL" \
  --native-path "$MAXKB_OPENAI_PATH" \
  --output .local-services/maxkb_local/logs/smoke
```

The adapter records API discovery and native QA. It does not treat internal
source routes as a stable public direct-retrieval API: until the running
instance exposes an authenticated retrieval/hit-test contract, ingestion and
direct retrieval remain `unsupported` rather than being guessed.
