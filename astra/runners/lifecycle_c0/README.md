# Product-neutral C0 lifecycle controller

This package is the shared clean lifecycle path for Astra and Hermes
Terminal-Bench runs. It is outside the tested product process tree and uses
only Harbor's environment interface plus two container-side, read-only probes.

```text
Harbor host agent
  ├─ controller.jsonl
  ├─ C0Controller ── polls task predicate through a separate container exec
  └─ process supervisor ── starts the tested product in a new session
                           └─ Astra CLI or Hermes gateway driver
```

The process supervisor is reused from `astra_smoke/probe.py`; the lifecycle
package does not duplicate its future F1 process-tree logic. C0 itself has no
kill, signal, restart, recovery, or workspace-write action. After a stable
trigger hit it records exactly:

```json
{"event":"fault_action","action":"noop","executed":true}
```

For C0, the shared supervisor's optional strict mode enforces the container-side
product deadline and always performs an identity-checked process-tree teardown
before publishing `product.cleanup.json`. It is a Linux child subreaper, so the
proof includes detached or daemonized descendants even if the registered root
exits first. Deadline/cancellation teardown is recorded separately as
`product_process_cleanup` with `fault_action=false`; it never substitutes for
the trigger-phase no-op.

The four task-specific predicates inspect only external task state:

| Task | Stable nonterminal predicate |
|---|---|
| `modernize-scientific-stack` | One, but not both, required output classes is ready |
| `overfull-hbox` | `input.tex` changed and no clean `main.log` exists |
| `build-pmars` | Debian source metadata and `src/Makefile` exist before install |
| `db-wal-recovery` | WAL magic is valid before `recovered.json` exists |

Their instruction hashes must match exactly. Other Terminal-Bench tasks use a
deterministic generic `product-live` predicate: after the controller has read a
registered process identity, it observes static read-only evidence twice and
then revalidates that exact live process before recording the no-op. This is a
generic lifecycle point, not a task-progress trigger. Metadata keeps the scope
explicit, and all current C0 runs remain exploratory and ineligible for formal
C0/F1 pairing. Each predicate observation is read without following symlinks,
and the same evidence hash must be observed twice. The controller records both
the manifest hash and the predicate probe source hash.

`no_hit` is a normal experimental outcome. It leaves the upstream verifier
enabled and sets the lifecycle gate to false; it is not rewritten as an
infrastructure error. Malformed process identity, malformed probe output, or a
probe execution failure fails closed as a controller infrastructure error.
Before recording the no-op, the controller also revalidates the registered
root's live process fingerprint. Terminal evidence distinguishes
`product_exited`, `product_timeout`, `product_cancelled`, and controller trigger
timeout, while the metadata and audit preserve the product terminal status and
zero-live cleanup-report hash.

Audit a completed job tree without rerunning either product:

```bash
cd "$(git rev-parse --show-toplevel)"
PYTHONPATH="$PWD" python3 -m astra.runners.lifecycle_c0.audit \
  "work/astra-c0-lifecycle-jobs"
```

The audit is read-only by default. Add `--write` only when per-trial
`c0-audit.json` sidecars are wanted.

F1 is intentionally not implemented here yet. When it is added, C0 and F1 must
continue through this same wrapper, trigger, budget, and event collection path;
only the registered action object may change from `noop` to the frozen fault.
