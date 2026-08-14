# Astra + Harbor 0.20 lifecycle smoke

This runner performs a narrow **CLI execution-plane smoke test**. It does not
claim that the whole Astra service was killed, and it does not prove automatic
recovery. F1 freezes and kills one supervised Astra CLI process tree and then
explicitly relaunches the CLI with the same Astra session ID.

## Contract

- A host-provided Linux ELF Astra artifact is uploaded to the Harbor task
  container. The existing macOS `target/release/astra` is rejected.
- The Astra API and databases remain outside the killed process group. For the
  local Docker smoke, `ASTRA_API_URL` must use `host.docker.internal`.
- The bundled local task uses public container networking because Harbor's
  Docker provider cannot enforce no-network/allowlist policies on Docker
  Desktop for macOS. The agent still rejects API URLs whose host is not
  `host.docker.internal`; use a network-policy-capable Linux provider for a
  formal isolation claim.
- A fixed first turn must return exactly `READY` with zero tool calls. Its
  server-issued `session_id` is pinned for the task and optional relaunch.
- C0 and F1 observe the same `path_exists` trigger. C0 records a no-op. F1
  uses a Linux child subreaper, revalidates the registered launcher and root,
  binds each target with a pidfd, freezes the full descendant tree to a stable
  boundary, and sends `SIGKILL` leaf-to-root. It fails closed on any identity
  mismatch, unsafe target, missing descendant, unstable tree, or survivor.
- Every turn in one trial uses the same isolated `HOME` and credentials
  directory. The runner seeds only a minimal access-token profile in that
  temporary directory; it never copies the host refresh token or other
  profiles. C0 and F1 still run as independent trials with new sessions.
- Ground-truth events are appended on the host to
  `controller.jsonl` under Harbor's agent `logs_dir`. Prompts, tokens, and
  credentials are excluded.

The `path_exists` predicate is only instrumentation for this infrastructure
smoke. Detached descendants are retained beneath the dedicated subreaper and
included even when they create a new process group or POSIX session. A valid
F1 also proves that the task-owned checkpoint is still pending and the terminal
artifact is absent before relaunch, then requires a recovery tool action and
the expected completed checkpoint and artifact after relaunch. This remains a
local smoke rather than a scored v0.4 benchmark run.

## Prerequisites

1. Harbor is exactly `0.20.0` and Docker is healthy.
2. Astra API is reachable from a container at
   `http://host.docker.internal:17001`.
3. `ASTRA_ACCESS_TOKEN` is a short-lived token for the local Astra server.
4. `ASTRA_SMOKE_LINUX_BINARY` points to an `x86_64` or `aarch64` Linux ELF
   matching the task container, not the local Mach-O build.
5. `ASTRA_SMOKE_MODEL` names one enabled model on the Astra server.

The bundled `tasks/astra-lifecycle-smoke` task creates
`/tmp/astra-smoke/trigger` after atomically persisting `phase-1` and a
`resume-required` checkpoint, leaves an eight-second injection window, and
uses a deterministic verifier. The checkpoint itself contains the public
resume command, so the runner does not replay the interrupted instruction.
It is intentionally an infrastructure smoke task rather than a
Terminal-Bench score.

## Run

The C0 and F1 configs are ready as `example-job.yaml` and
`example-job-f1.yaml`. Export values without writing the token into YAML:

```bash
cd "$(git rev-parse --show-toplevel)"

./astra/runners/astra_smoke/build-linux.sh

export ASTRA_API_URL=http://host.docker.internal:17001
export ASTRA_ACCESS_TOKEN='replace-with-short-lived-token'
export ASTRA_SMOKE_LINUX_BINARY="$PWD/work/astra-linux-build/target/release/astra"
export ASTRA_SMOKE_MODEL='replace-with-enabled-model-id'
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

harbor --version
harbor run --config astra/runners/astra_smoke/example-job.yaml --print-config
harbor run --config astra/runners/astra_smoke/example-job.yaml --yes
harbor run --config astra/runners/astra_smoke/example-job-f1.yaml --yes
```

Inspect the trial's agent log directory. A valid F1 hit must contain, in order,
`product_process_registered`, `trigger_observed`, an executed
`freeze_kill_tree_sigkill` with no survivors, a successful task-environment
post-fault probe, `workspace_checkpoint_post_fault_probe`,
`terminal_artifact_post_fault_probe`, a recovery relaunch with tool calls, and
the two post-relaunch workspace probes. It must finish with
`lifecycle_gate_passed: true`. A no-hit is retained as `trigger_no_hit` and
fails the smoke gate; the runner never moves the trigger after observing the
result.

Audit a completed Harbor job from persisted evidence:

```bash
python3 -m astra.runners.astra_smoke.audit \
  "$PWD/work/astra-smoke-jobs/<job>"
```

The audit fails unless the controller event order, pinned session, condition
semantics, same-session F1 relaunch, and Harbor reward all pass.

Run dependency-free unit tests without Docker or credentials:

```bash
python3 -m unittest discover -s astra/runners/astra_smoke/tests -v
```
