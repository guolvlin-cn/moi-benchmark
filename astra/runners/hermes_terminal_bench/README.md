# Hermes Terminal-Bench S0 and C0 runners

This configuration runs Harbor 0.20's built-in Hermes implementation through a
thin adapter that only adds `condition: S0` and `fault_injected: false` result
metadata. It uses the same four unmodified Terminal-Bench tasks as the Astra S0
exploratory run, the upstream task verifier, and no lifecycle wrapper or
injected fault.

The four-case job is exploratory. The built-in adapter installs the frozen
`v2026.7.20` Hermes tag independently in every task container. Formal scoring
still requires freezing and recording the resolved commit, dependencies, and
configuration hashes.

## Run

Hermes connects directly to Z.AI for `zai/glm-5.2`; the Astra API and databases
are not required. Supply the key through the process environment or a private
env file, never in this repository.

```bash
cd "/Users/chenyuwei/Documents/MOI benchmark"

export GLM_API_KEY='replace-with-your-key'

harbor run \
  --config "/Users/chenyuwei/Documents/MOI benchmark/astra/runners/hermes_terminal_bench/s0-four-cases.yaml" \
  --yes
```

Or put `GLM_API_KEY=...` in a private file and add
`--env-file /absolute/path/hermes.env`.

Results are written to `work/hermes-s0-jobs`. Each trial should retain
`agent/hermes.txt`, `agent/hermes-session.jsonl`, and, when conversion succeeds,
`agent/trajectory.json`.

This S0 config keeps each task's upstream timeout. Any extended-budget run must
use the same per-task budget for Astra and Hermes and write to separate result
directories.

Harbor's built-in Hermes adapter runs its headless CLI with automatic approval.
That path is used here only for ordinary S0 testing; it must not be reused for
C0/F1 lifecycle or fault evaluation.

## C0 lifecycle run

`c0-four-cases.yaml` uses `HermesTerminalBenchC0Agent`, not Harbor's stock
`hermes --yolo chat` execution path. The adapter starts
`hermes gateway run --no-supervise` as a foreground child and submits the task
through Hermes' Runs API. This gives the external lifecycle controller one
real process tree containing the driver, gateway, agent, and tool processes.

The C0 approval policy is frozen as follows:

- Hermes native `approvals.mode: smart` remains enabled by a Harbor read-only
  directory bind mount at `/etc/hermes` containing `config.yaml` and `.env`.
  Mounting the directory, rather than only one file, also prevents a root agent
  from moving the parent aside and recreating an unmanaged `/etc/hermes`.
- The managed layer also pins the empty permanent allowlist, disables quick
  commands, shell hooks, and MCP servers/reload, fixes the model/tool/terminal
  policy, and disables memory and checkpoints. A fail-closed Python startup
  guard loads before Hermes application imports and pins the managed directory,
  YOLO, hook acceptance, approval prompting, gateway key, and selected provider
  key in the gateway process. This prevents Hermes' per-turn user-`.env` reload
  from redirecting or weakening the managed policy. The driver unwraps
  install.sh's user-facing launcher and executes its real venv entrypoint,
  because that launcher deliberately clears `PYTHONPATH`.
- A native smart decision may approve or deny a command internally.
- Any decision that remains unresolved and reaches the Runs API is
  deterministically denied. The runner never answers `once`, `session`, or
  `always`.
- The runner does not enable YOLO mode or approval-hook acceptance.

Run the four exploratory cases with:

```bash
cd "/Users/chenyuwei/Documents/MOI benchmark"

export GLM_API_KEY='replace-with-your-key'

harbor run \
  --config "/Users/chenyuwei/Documents/MOI benchmark/astra/runners/hermes_terminal_bench/c0-four-cases.yaml" \
  --yes
```

### Preinstalled C0 images

The on-demand path pays the Hermes installation cost once while still creating
a fresh container for every trial. It retains one shared
`moi/hermes-tbench-runtime:v2026.7.20` payload, but it never prebuilds all task
images. At least one task must be named explicitly, either as an argument or in
a queue file.

For one task:

```bash
cd "/Users/chenyuwei/Documents/MOI benchmark"

export GLM_API_KEY='replace-with-your-key'

/bin/bash astra/runners/hermes_terminal_bench/prebuilt/build-images.sh \
  modernize-scientific-stack
```

The shared preinstalled runtime freezes ZAI's
`ProviderProfile.fixed_temperature` at `0.0`, so each primary GLM-5.2 Chat
Completions request explicitly sends `temperature: 0.0`; it does not fall back
to the provider default. A non-zero Docker build argument fails closed. The
queue detects a retained runtime with a different temperature or audit digest
and rebuilds it automatically.

This sampling patch applies only to the preinstalled
`c0-four-cases-prebuilt.yaml` path. The runtime-install
`c0-four-cases.yaml` path still uses the unmodified frozen Hermes source and
therefore omits temperature. It covers the primary ZAI Chat Completions path,
not auxiliary model calls used by features such as title generation or context
compression.

For several tasks passed directly:

```bash
/bin/bash astra/runners/hermes_terminal_bench/prebuilt/build-images.sh \
  modernize-scientific-stack \
  overfull-hbox \
  build-pmars \
  db-wal-recovery
```

For a queue file, put one task directory basename on each line (for example,
`overfull-hbox`, not the TOML name `terminal-bench/overfull-hbox`). Blank
lines, comments, and duplicates are ignored while first-seen order is
preserved:

```bash
/bin/bash astra/runners/hermes_terminal_bench/prebuilt/build-images.sh \
  --queue-file \
  astra/runners/hermes_terminal_bench/prebuilt/c0-four-cases.queue.txt
```

The queue is strictly serial. For each entry the script:

1. reads that task's original `docker_image`;
2. builds only
   `moi/hermes-tbench-<task>:v2026.7.20` with `--no-cache`;
3. verifies the frozen Hermes and Playwright runtime;
4. creates an isolated task configuration copy and runs only that task through
   Harbor; and
5. removes the managed derived image before moving to the next entry.

The same cleanup is attempted after build, Harbor, timeout, interrupt, and
failure paths. A cleanup failure aborts the queue so a later entry cannot hide
a retained image. As with any shell cleanup trap, an uncatchable `SIGKILL` or
Docker daemon crash can still leave artifacts behind. The original
Terminal-Bench image, shared Hermes runtime, and Harbor result directory are
not deleted. Each Harbor trial still starts a new container, so one task's
writable container state is not reused by the next.

`--no-cache` prevents reusing build results, and no runnable derived task image
tag is retained. Docker BuildKit may still keep untagged internal content blobs
under its own storage policy. The script intentionally does not run a global
`docker builder prune`, because that would delete caches belonging to other
projects.

Git clone, Python/uv dependency installation, Node installation, and the
Playwright browser download happen only in the retained shared runtime.
Debian/Ubuntu system libraries are resolved anew against the queued task's
base. The large runtime payload remains content-addressed and shared rather
than being installed from the network in each task.

By default the runtime builder reuses the already-required local
`alexgshaw/modernize-scientific-stack:20251031` Debian 12/amd64 image. The
final `scratch` payload copies only Hermes runtime paths, so `/app` and other
task files from that builder are not included. This also avoids an additional
Docker Hub pull for `debian:12-slim`.

The shared runtime tag is a payload-only `scratch` image, not a standalone
container. The queue script automatically smoke-checks every temporary derived
image's Hermes version, live Git commit, Playwright dependency closure, browser
executable, and unresolved dynamic libraries. It also creates the isolated
task copy and invokes Harbor; a separate `prepare_tasks.py` or `harbor run`
command is not required.

The selected buildx builder must use the Docker engine `docker` driver; the
script fails before building if an isolated `docker-container` builder is
active, because that builder cannot resolve the retained local runtime tag.
The script also refuses to overwrite a runtime or task image tag unless its
management labels match this runner.

Only one queue may own the workspace's derived image tags at a time. An atomic
lock at `work/.hermes-prebuilt-image-queue.lock` prevents concurrent runners
from deleting each other's images. If an uncatchable crash leaves this empty
directory behind, first confirm no queue is active and remove that exact empty
directory with `rmdir`.

```bash
/bin/bash astra/runners/hermes_terminal_bench/prebuilt/build-images.sh \
  --print-queue \
  --queue-file \
  astra/runners/hermes_terminal_bench/prebuilt/c0-four-cases.queue.txt
```

`--print-queue` validates and displays the de-duplicated queue without using
Docker. Running the script without a task or `--queue-file` is an error.

The four original cases retain their task-specific progress predicates. Other
Terminal-Bench 2.1 tasks use the read-only
`terminal-bench.generic.product-live` predicate, with the product budget
derived from that trial's `[agent].timeout_sec` and multiplied by two. These
generic cases are exploratory C0 coverage: their trigger is not a
task-semantic fault-injection point and cannot be treated as an F1 pairing.
The on-demand builder does not prebuild a dataset-sized image set. Its default
four-case config rejects other tasks before Docker starts; generic/full tasks
must use `c0-all-prebuilt.yaml`, as the full wrapper does.

The queue always tells Harbor not to force-build the original Dockerfile. The
runner skips network installation only after verifying the immutable marker,
absolute Hermes launcher, frozen release, and live source commit. A missing or
mismatched marker fails closed instead of falling back to an unpinned runtime
install. No API key, managed policy, session, trajectory, or controller code is
baked into these images.

The retained runtime records the normalized temperature, application point,
configurator digest, and effective source-patch digest in
`/opt/moi/hermes-preinstalled.json` and
`/opt/moi/hermes-temperature.json`. The same temperature and configurator
digest are OCI labels, and each task-image smoke check imports the real ZAI
provider and verifies its `fixed_temperature` before Harbor starts:

```bash
docker image inspect moi/hermes-tbench-runtime:v2026.7.20 \
  --format '{{ index .Config.Labels "io.moi.hermes-tbench.temperature" }}'
```

The controller's temperature-policy validation remains unchanged. Its existing
`hermes_prebuilt_marker_sha256` result field binds a trial to the exact marker
bytes, including these sampling fields, but does not interpret or enforce them.
The fixed-zero guarantee therefore applies to the prescribed
`build-images.sh` path, which verifies the image before starting Harbor.
Directly running an image that bypasses that build and smoke-check path is
outside this image-only guarantee.

## Full 89-task exploratory C0 run

The full runner requires Terminal-Bench commit
`5c8eadf1f393183288fa08b8f73ca9a469cc5e00`, rejects local changes under
`tasks/`, validates the pinned 89-task queue, builds and deletes one thin task
image at a time, discovers already-recorded terminal trials, and aggregates
the 89 independent Harbor jobs into one JSON and CSV summary. It records a
cohort fingerprint in the jobs directory and refuses to resume if the
controller, managed policy, lifecycle probes, runtime builder, full config, or
dataset identity changed. The same identity is rechecked before and after every
queued task, preventing a long-running invocation from silently mixing result
generations.
Checking the queue does not start Docker, Harbor trials, or model calls:

```bash
cd "/Users/chenyuwei/Documents/MOI benchmark"

/bin/bash astra/runners/scripts/hermes-terminal-bench-all-c0.sh \
  --check
```

Run all currently missing tasks:

```bash
cd "/Users/chenyuwei/Documents/MOI benchmark"

export GLM_API_KEY='replace-with-your-key'

/bin/bash astra/runners/scripts/hermes-terminal-bench-all-c0.sh
```

For a bounded batch, and then resume later with the same command:

```bash
/bin/bash astra/runners/scripts/hermes-terminal-bench-all-c0.sh \
  --max-tasks 5
```

Reward-zero trials and terminal exceptions are recorded results and are
skipped on normal resume. Pass `--retry-errors` to retry only tasks whose
latest recorded trial is an exception, `--retry-audit-failures` to retry tasks
whose strict C0 status is `no_hit` or `infra_error`, or `--rerun-all` to
deliberately schedule all 89 tasks again. The aggregate always selects the
latest finished attempt for each task; it is not a pass@k or multi-attempt
mean.

The per-task Harbor jobs remain under
`work/hermes-c0-all-jobs`. Queue-level outputs are updated under
`work/hermes-c0-all-state`:

- `summary.json` contains coverage, verifier status, strict offline C0 evidence
  status, task-specific/generic trigger-scope counts, token totals,
  dataset/cohort identity and fingerprint, hashes, and each selected trial
  result path.
  Results from a different agent, model, version, or install mode are ignored
  rather than mixed into the cohort.
- `summary.csv` is the flat task-level result table. `reward` preserves the
  upstream value while `scored_reward` is zero for exceptions or missing
  verifier rewards.
- `pending.queue.txt` is the next resumable batch.

The aggregate mean counts a recorded exception or missing verifier reward as
zero. Verifier outcome and C0 audit outcome are separate. The C0 column invokes
the repository's offline `audit_trial` validator over the controller ledger,
cleanup report, managed policy/guard, trajectory/session evidence, hashes, and
trigger ordering; the prebuilt marker must also be verified. Outcomes are
`passed`, `no_hit`, or `infra_error`, so reward 1 cannot hide invalid lifecycle
evidence.

The 89 upstream agent timeouts total about 42.2 hours. Their two-times product
budgets total about 84.4 hours sequentially, before image builds, setup, and
verifiers. Docker deletes each Hermes-derived task image but retains the
shared runtime, original task base images, and BuildKit layers.

The default run schedules one attempt per task; explicit retry options can
create later attempts, of which only the latest finished one is selected. It
uses modified product timeouts, derived task images, and task images pinned by
tag rather than digest. Its metadata remains
`evaluation_status=exploratory_unfrozen` and
`formal_score_eligible=false`; it is not an official Terminal-Bench
leaderboard submission.

The full wrapper also holds `work/.hermes-c0-all-run.lock`. If an uncatchable
`SIGKILL` leaves that empty directory behind, first confirm no full wrapper is
running and remove exactly that lock with:

```bash
rmdir "/Users/chenyuwei/Documents/MOI benchmark/work/.hermes-c0-all-run.lock"
```

The controller uses each task's upstream agent timeout multiplied by two. For
the original four cases this is 1200 seconds for
`modernize-scientific-stack`, 1500 for `overfull-hbox`, and 1800 for
`build-pmars` and `db-wal-recovery`; the full dataset reaches 24000 seconds for
`build-pov-ray`. The driver receives that task-specific product budget. A
separate `agent_timeout_multiplier: 2.25` reserves wrapper time for setup,
gateway shutdown, external zero-live proof, terminal ledger persistence, and
bounded trajectory export; it cannot extend model execution.
The direct C0 config writes to `work/hermes-c0-lifecycle-jobs`; the on-demand
preinstalled queue writes to `work/hermes-c0-prebuilt-lifecycle-jobs`. In
addition to the normal Harbor result, each trial records:

- `agent/hermes-gateway.txt`
- `agent/hermes-managed-config.yaml`
- `agent/hermes-managed.env`
- `agent/hermes-policy-guard.py`
- `agent/hermes-policy-guard.jsonl`
- `agent/hermes-run.json`
- `agent/hermes-run-events.jsonl`
- `agent/hermes-driver.stdout.txt`
- `agent/hermes-driver.stderr.txt`
- `agent/product.identity.json`
- `agent/product.cleanup.json`
- `agent/hermes-session.jsonl` and, when conversion succeeds,
  `agent/trajectory.json`

Both `hermes-run-events.jsonl` and `hermes-session.jsonl` are required
trajectory evidence. The driver appends each Runs API event directly to
Harbor's mounted trial directory while the run is active. A valid event stream
has exactly one `run.submitted` for the current run/session, exactly one
matching terminal, and no mismatched run or session IDs. Native terminals are
`run.completed`, `run.failed`, and `run.cancelled`. When the driver deadline
expires, the driver first requests native stop and waits up to eight seconds
for a native terminal without extending the product budget. If Hermes still
does not emit one, the driver durably appends `run.timed_out` with
`source=driver`, `reason=ProductDeadlineExpired`, and matching run/session
IDs before it stops the Gateway. A native and driver terminal in the same
stream, or a driver timeout with any other source/reason, fails validation.

After product-tree cleanup, the adapter runs
`hermes sessions export /logs/agent/hermes-session.jsonl --session-id <id>`.
The one-session JSONL export must match the preallocated session ID and contain
at least one message. The controller records hashes and counts for both
artifacts. Timeout and cancellation paths still make this export through a
bounded, shielded finalizer. `controller_completed` remains the last ledger
event and explicitly records `saved` or `failed`; a failed required capture
cannot masquerade as complete lifecycle evidence, but it does not raise an
agent infrastructure exception or block the Terminal-Bench verifier.
`trajectory.json` remains an optional ATIF conversion derived after the run.
Metadata records `trajectory_terminal_event`,
`trajectory_terminal_event_source`, and `trajectory_terminal_reason`, so a
complete driver-deadline trajectory cannot be confused with native Hermes
completion. Historical streams are never backfilled and retain their legacy
incomplete classification.

The gateway API key is generated inside the driver and is never written to
these files. Provider credentials are removed from the adapter's general
execution environment. Each run uploads one mode-0600 credential file under
its random control directory; the driver reads and deletes it before starting
the gateway, so the secret never appears in a Docker Compose command line.
The provider key is registered again only after Harbor 0.20 snapshots the run
environment, allowing Harbor's final text-artifact scrub to redact it without
injecting it into setup, controller, or task commands.
Before installing or starting Hermes, the adapter verifies that both managed
policy files match the repository copies and that `/proc/self/mountinfo`
marks `/etc/hermes` read-only. It verifies the startup guard bytes after
upload, the resolved approval mode is `smart`, and
`hermes config set approvals.mode off` is rejected. The driver will not submit
a run unless the gateway itself writes matching guard-load evidence with its
PID. All three SHA-256 values and the active-guard result are copied into the
controller ledger and result metadata.
The gateway's final SIGTERM (and a last-resort SIGKILL if graceful cleanup
stalls) is recorded as normal post-run cleanup with
`fault_action: false`; it is not a C0 or F1 fault.
The shared Linux supervisor then verifies that the driver, gateway, tools, and
any subreaper-adopted descendants are all gone before setting `product_done`.
The host ledger hashes this report and records `product_terminal_status`
(`completed`, `failed`, `timeout`, or `cancelled`) before optional exports.

This four-case C0 job is exploratory and not scoreable. The tag
`v2026.7.20` and model `zai/glm-5.2` are frozen, but formal scoring still
needs a recorded resolved Hermes commit/dependency manifest, a frozen
task-specific trigger manifest, and approval/tool-policy parity with Astra.
The Runs API exposes escalated approvals but not every internal smart
classifier decision, so those native decisions cannot yet be independently
reconstructed from the runner ledger. No F1 behavior is implemented here.
