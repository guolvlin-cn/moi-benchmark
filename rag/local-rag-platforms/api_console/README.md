# MOI RAG API Console

Loopback-only FastAPI control plane for the local MOI baseline plus Dify,
FastGPT, MaxKB and RAGFlow deployments. It shows Docker/runtime status,
performs health probes, edits an allowlist of API configuration fields, and
enforces the one-competitor-at-a-time policy for competitor service starts.
MOI is the baseline and is therefore exempt from that mutex.

Security properties:

- binds to `127.0.0.1` only;
- never returns stored secret values to the browser;
- accepts mutations only with the per-process console token embedded in the
  same-origin page;
- writes runtime env files atomically with mode `0600`;
- keeps action logs under ignored `.local-services/api-console/`;
- disables RAGFlow start while its local resource gate is blocked.

The MOI card controls its existing `matrixone` and `moi-openxml-parser`
containers. Its only editable secret is `TAAS_API_KEY` in
`prototypes/local-matrixflow-rag/.env`; model IDs and provider URLs remain in
the benchmark's versioned JSON configuration.

All five cards also expose optional Baidu Qianfan V2 fields. Saving those
fields stores credentials only; each vendor UI/adapter must still register and
probe its own OpenAI-compatible provider. Qianfan embeddings always require a
new dataset/vector table and full re-index.

Install and start:

```bash
python3 -m venv .local-services/api-console/.venv
.local-services/api-console/.venv/bin/pip install -r local-rag-platforms/api_console/requirements.txt
nohup .local-services/api-console/.venv/bin/uvicorn app:app \
  --app-dir local-rag-platforms/api_console \
  --host 127.0.0.1 --port 8765 \
  >.local-services/api-console/server.log 2>&1 &
```

Open <http://127.0.0.1:8765>. Runtime PID and logs belong under
`.local-services/api-console/` and are not committed.
