# Pi Terminal-Bench C0 runner

This runner adds Harbor 0.20.0's built-in Pi product version to the MOI C0
comparison. It fixes the product package at
`@mariozechner/pi-coding-agent@0.73.1`; the wrapper does not modify Pi source.

The run is C0, not S0: the real Pi process group is launched by the shared
lifecycle supervisor, observed by the shared controller, and receives one
registered no-op control action with `fault_injected=false`. The four frozen
fault-compatible tasks use their task-specific progress predicates. The other
85 tasks use `terminal-bench.generic.product-live`.

The local adapter replaces Harbor's stock shell pipeline for two protocol
reasons. It passes the instruction through stdin so leading-hyphen tasks are
not interpreted as CLI options, and it supervises `/usr/local/bin/pi` rather
than a `grep | tee` pipeline. Pi stdout JSONL, stderr, saved session, identity,
and cleanup report are persisted separately. The supervisor omits only the
high-volume `message_update` and `tool_execution_update` deltas from the saved
JSONL; terminal messages and tool start/end events remain available for C0
trajectory validation.

Pi 0.73.1 does not contain `zai/glm-5.2` in its built-in registry. The runner
supplies the documented custom model profile from `managed/models.json` and
requires every assistant event to report exactly `zai/glm-5.2`. A fallback to
another model makes the C0 audit fail.

## Check the 88-task queue

```bash
cd "$(git rev-parse --show-toplevel)"

HARBOR_BIN="$HOME/.local/share/uv/tools/harbor/bin/harbor" \
MOI_BENCH_DATA_ROOT="$PWD" \
  /bin/bash astra/runners/scripts/pi-terminal-bench-all-c0.sh --check
```

## Smoke one task

```bash
export ZAI_API_KEY='replace-with-your-key'
export HARBOR_BIN="$HOME/.local/share/uv/tools/harbor/bin/harbor"
export MOI_BENCH_DATA_ROOT="$PWD"
# Optional when host downloads should use the local mixed/HTTP proxy:
export PI_TBENCH_CACHE_PROXY_URL="http://127.0.0.1:7892"

  /bin/bash astra/runners/scripts/pi-terminal-bench-all-c0.sh --max-tasks 1
```

To run an explicit retry cohort even when those tasks already have verifier
results, pass its resource queue with `--retry-queue`:

```bash
/bin/bash astra/runners/scripts/pi-terminal-bench-all-c0.sh \
  --retry-queue \
  "$MOI_BENCH_DATA_ROOT/work/pi-c0-all-state/retry-balance-plus-unfinished.queue.tsv"
```

The generated queue is largest-memory and longest-timeout first, so the first
smoke is intentionally an 8GB case. The scheduler reserves 2GB of the 8GB host
budget for Docker/Harbor when tasks declare at most 4GB: a 4GB task can pair
with one 2GB task, and at most three 2GB tasks overlap. A declared 8GB task gets
the machine alone and may use the configured 1GB swap as host pressure margin.
CPU reservations are capped at 6 of the 8 host CPUs except for an isolated
8GB task. Do not lower task resource declarations to increase concurrency;
that would change the benchmark.

The thin-image builder retains one Pi/Node runtime image and derives a task
image from each queued task base. This avoids 88 independent NVM/npm
installs. Each trial still receives a fresh Harbor container.

Results are written to `work/pi-c0-all-jobs`. The common lifecycle audit must
report both a C0 hit/no-op result and a valid Pi JSONL/session pair. Product
reward and C0 validity remain separate fields. A timeout may leave a partial
Pi stream; the artifact is hashed and reported as a non-blocking trajectory
failure while process cleanup and the C0 no-op remain strict.

The Pi cohort also uses a fail-closed Terminal-Bench verifier. A reward is
scored only when `verifier/ctrf.json` proves that pytest executed at least one
test. Bootstrap failures such as DNS, package-install, or SSL errors remain
pending for rerun instead of being recorded as task failures with reward 0.

Before model execution, the runner caches Linux/amd64 `uv`/`uvx` 0.9.5 and
the CPython standalone archives needed by the 82 scripts that use uv in the
88-task Pi cohort (3.11, 3.12, and 3.13) under
`work/pi-verifier-cache`. After each agent
finishes, the custom verifier copies only uv and the requested Python archive
into that trial's container, including the one task whose image already
contains uv 0.8.15.
The original test script is unchanged; a verifier-only curl wrapper intercepts
only the exact uv installer URL because uv is already preinstalled, and uv
reads the CPython release from a local `file://` mirror. PyPI packages and
task-specific downloads still use the configured Docker network/proxy. The
cache is not mounted during the agent phase and is never written back from a
trial.

Each verifier limits uv to two concurrent downloads. The outer scheduler runs
at most three 2GB jobs, so one runner creates at most six concurrent uv
downloads. A 4GB plus 2GB pair creates at most four, and an isolated 8GB job
creates at most two. Independently started runner processes are outside this
bound and should not share the same cold proxy run.

The Pi queue deliberately excludes `tune-mjcf`. See
[DOWNLOAD_CACHE_INVENTORY.md](DOWNLOAD_CACHE_INVENTORY.md) for the resulting
88-task audit and its cache priorities.
