#!/usr/bin/env python3
"""Authorized lifecycle entrypoint for post-hoc unavailable/infra reruns.

The formal M2/M3 evidence is never opened for writing.  This wrapper installs
the already-audited outer lifecycle compatibility layer and adds only the
frozen, container-local preprocess overlay required by
``filter-low-selling-products``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path("/home/vagrant/moi-benchmark")
DEFAULT_POLICY = (
    REPO_ROOT
    / "astra/benchmark/toolathlon-verified/config/"
    "posthoc-unavailable-infra-rerun-policy.v1.json"
)
BATCH_MANIFEST = "posthoc-rerun-manifest.json"


class AuthorizationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuthorizationError(f"expected JSON object: {path}")
    return value


def load_hotfix(policy: dict[str, Any]) -> ModuleType:
    runtime = policy.get("runtime")
    if not isinstance(runtime, dict):
        raise AuthorizationError("rerun policy has no runtime object")
    relative = Path(str(runtime.get("lifecycle_hotfix_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise AuthorizationError("unsafe lifecycle hotfix path")
    helper = (REPO_ROOT / relative).resolve()
    if helper != REPO_ROOT / relative or sha256_file(helper) != runtime.get(
        "lifecycle_hotfix_sha256"
    ):
        raise AuthorizationError("lifecycle hotfix differs from rerun policy")
    spec = importlib.util.spec_from_file_location(
        "toolathlon_posthoc_outer_lifecycle", helper
    )
    if spec is None or spec.loader is None:
        raise AuthorizationError("cannot load lifecycle hotfix")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def option_value(values: list[str], option: str) -> str:
    try:
        index = values.index(option)
        return values[index + 1]
    except (ValueError, IndexError) as exc:
        raise AuthorizationError(f"lifecycle invocation has no {option}") from exc


def authorize_invocation(
    values: list[str], policy_path: Path, policy: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    output = Path(option_value(values, "--output-dir")).resolve()
    run_id = option_value(values, "--run-id")
    task_id = option_value(values, "--task-id")
    system_id = option_value(values, "--system")
    experiment_id = option_value(values, "--experiment-id")
    if len(output.parents) < 4:
        raise AuthorizationError("rerun output path is too shallow")
    batch_root = output.parents[3]
    manifest = read_object(batch_root / BATCH_MANIFEST)
    if (
        manifest.get("schema_version")
        != "toolathlon.posthoc-unavailable-infra-rerun-manifest.v1"
        or manifest.get("policy_sha256") != sha256_file(policy_path)
        or manifest.get("formal_result_mutation") is not False
        or experiment_id != policy.get("runtime", {}).get("experiment_id")
    ):
        raise AuthorizationError("post-hoc rerun batch authorization differs")
    matching = [
        item
        for item in manifest.get("cases", [])
        if isinstance(item, dict)
        and item.get("task_id") == task_id
        and item.get("system_id") == system_id
        and run_id in item.get("target_run_ids", [])
    ]
    if len(matching) != 1:
        raise AuthorizationError("lifecycle run is not selected by the rerun manifest")
    expected = batch_root / "runs" / system_id / task_id / run_id
    if output != expected:
        raise AuthorizationError("lifecycle output path differs from rerun manifest")
    return batch_root, matching[0]


def install_posthoc_dataset_overlay(
    lifecycle_module: Any,
    hotfix: ModuleType,
    *,
    policy_path: Path,
    batch_root: Path,
) -> None:
    current = lifecycle_module.SingleTaskLifecycle._copy_tree

    def copy_tree(self: Any) -> None:
        current(self)
        if self.args.task_id != hotfix.DATASET_REPAIR_TASK:
            return
        if (
            self.args.system != "astra"
            or self.args.experiment_id
            != "toolathlon-verified-v0.5-posthoc-rerun-v1"
            or self.output.parents[3] != batch_root
        ):
            raise AuthorizationError(
                "post-hoc dataset preprocess overlay is not authorized"
            )
        source_projection = hotfix._dataset_repair_source_projection(self.source)
        target = f"/workspace/{hotfix.DATASET_REPAIR_SOURCE_RELATIVE}"
        script = (
            "import hashlib,json,pathlib,sys; "
            "p=pathlib.Path(sys.argv[1]); b=p.read_bytes(); "
            "assert hashlib.sha256(b).hexdigest()==sys.argv[2]; "
            "s=b.decode('utf-8'); changes=json.loads(sys.argv[4]); "
            "assert all(s.count(x[0])==1 for x in changes); "
            "exec(\"for old,new in changes:\\n s=s.replace(old,new)\"); "
            "p.write_text(s,encoding='utf-8'); "
            "assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[3]"
        )
        self._docker(
            "exec",
            self.container_name,
            "python3",
            "-c",
            script,
            target,
            hotfix.DATASET_REPAIR_ORIGINAL_SHA256,
            hotfix.DATASET_REPAIR_PATCHED_SHA256,
            json.dumps(hotfix.DATASET_REPAIR_REPLACEMENTS, separators=(",", ":")),
            timeout=60,
        )
        overlay = {
            "schema_version": "toolathlon.dataset-preprocess-overlay.v1",
            "policy": "toolathlon.posthoc-filter-low-selling-products-overlay.v1",
            "task_id": self.args.task_id,
            "run_id": self.args.run_id,
            "system_id": self.args.system,
            "posthoc_rerun_policy": str(policy_path),
            "posthoc_rerun_policy_sha256": sha256_file(policy_path),
            "formal_result_mutation": False,
            "frozen_toolathlon_source_modified": False,
            **source_projection,
        }
        overlay_path = self.task_state / "preprocess-overlay.json"
        hotfix.write_json_atomic(overlay_path, overlay, mode=0o644)
        relative = overlay_path.relative_to(self.output).as_posix()
        self.lifecycle.append(
            "preprocess.overlay_applied",
            policy=overlay["policy"],
            overlay_artifact=relative,
            overlay_artifact_sha256=sha256_file(overlay_path),
            original_sha256=hotfix.DATASET_REPAIR_ORIGINAL_SHA256,
            patched_container_copy_sha256=hotfix.DATASET_REPAIR_PATCHED_SHA256,
            frozen_toolathlon_source_modified=False,
            formal_result_mutation=False,
        )

    lifecycle_module.SingleTaskLifecycle._copy_tree = copy_tree


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--posthoc-rerun-policy", type=Path, required=True)
    wrapper, lifecycle_values = parser.parse_known_args(values)
    policy_path = wrapper.posthoc_rerun_policy.resolve()
    if policy_path != DEFAULT_POLICY:
        raise AuthorizationError("unexpected post-hoc rerun policy path")
    policy = read_object(policy_path)
    if (
        policy.get("schema_version")
        != "toolathlon.posthoc-unavailable-infra-rerun-policy.v1"
        or policy.get("scope", {}).get("formal_result_mutation") is not False
    ):
        raise AuthorizationError("invalid post-hoc rerun policy")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    batch_root, _case = authorize_invocation(
        lifecycle_values, policy_path, policy
    )
    hotfix = load_hotfix(policy)
    hotfix.install_artifact_gate_hotfix()
    hotfix.install_model_usage_infra_hotfix()
    hotfix.install_agent_model_boundary_hotfix()
    hotfix.install_budget_evaluator_hotfix()
    from astra.runners.toolathlon_verified import lifecycle

    hotfix.install_lifecycle_count_scope_hotfix(lifecycle)
    hotfix.install_lifecycle_hermes_drain_reconciliation(lifecycle)
    hotfix.install_lifecycle_hermes_open_request_projection(lifecycle)
    hotfix.install_lifecycle_astra_deadline_observability(lifecycle)
    install_posthoc_dataset_overlay(
        lifecycle,
        hotfix,
        policy_path=policy_path,
        batch_root=batch_root,
    )
    return lifecycle.main(lifecycle_values)


if __name__ == "__main__":
    raise SystemExit(main())
