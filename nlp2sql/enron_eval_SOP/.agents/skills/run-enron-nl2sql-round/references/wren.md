# Wren round

## Preconditions

- Use a local Docker deployment of Canner/WrenAI.
- Require a private, actually mounted Wren AI Service `config.yaml` containing:

```yaml
model: openai/qwen3.7-plus-2026-05-26
```

- Restart or recreate the AI Service after changing the file.
- Connect the Wren project only to the six `enron_eval` MySQL tables.
- Do not add business instructions, curated SQL pairs, or extra semantic rules for the baseline condition.
- Keep `http://localhost:3000/api/v1/generate_sql` reachable.

Containers access the Mac host through `host.docker.internal`, not container-local `127.0.0.1`. If MySQL is correctly available only at host `::1:3306`, keep the repository's IPv4 bridge running on `127.0.0.1:13306` and configure Wren to use `host.docker.internal:13306`.

## Preflight

```bash
.venv/bin/python .agents/skills/run-enron-nl2sql-round/scripts/preflight.py \
  --product wren \
  --wren-config /absolute/path/to/wren/config.yaml
```

The passed file must be the private file mounted into the running AI Service, not merely the repository example.

## Run

```bash
.venv/bin/python scripts/run_one_round.py \
  --product wren \
  --run-id <run-id> \
  --wren-config /absolute/path/to/wren/config.yaml
```

The runner requests one independent Wren thread per question. A transport timeout or unreachable endpoint is a collector failure and stops the run without occupying that attempt. A normal API response with no SQL remains a product failure.

Wren's current endpoint may omit exact Token usage. Leave Token fields `null`; never estimate them.
