from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from astra.runners.toolathlon_verified.contract import (
    JsonlEventWriter,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)
from astra.runners.toolathlon_verified.lifecycle import (
    QUALIFICATION_TASK,
    SOURCE_COMMIT,
    TASK_IMAGE,
    LifecycleError,
    SingleTaskLifecycle,
    _free_port,
    _run,
    _safe_id,
    is_runtime_mutable_credential_record,
    load_task_reset_contract,
)
from astra.runners.toolathlon_verified.resources import ResourceSampler

from .orchestrator import PI_KEY_ENV, run as run_pi_slot
from .pi_adapter import PiRuntime


class PiSingleTaskLifecycle(SingleTaskLifecycle):
    """Reuse the verified task environment with a Pi-only product slot."""

    def preflight(self) -> None:
        if not self.task_source.is_dir():
            raise LifecycleError(f"task source is unavailable: {self.task_source}")
        self.task_reset_contract = load_task_reset_contract(
            task_id=self.args.task_id,
            task_source=self.task_source,
            requirements_path=self.freeze / "task-requirements.json",
        )
        if not self.host_python.is_file() or not self.runtime_overlay.is_file():
            raise LifecycleError("frozen Toolathlon runtime is unavailable")
        source_commit = _run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD^{commit}"],
            timeout=30,
        ).stdout.decode().strip()
        if source_commit != SOURCE_COMMIT:
            raise LifecycleError("Toolathlon source commit does not match the freeze")
        image = self._docker("image", "inspect", TASK_IMAGE, timeout=60)
        if not image.stdout:
            raise LifecycleError("frozen task image is not available")
        if not os.environ.get(PI_KEY_ENV):
            raise LifecycleError(f"required runtime credential is absent: {PI_KEY_ENV}")
        PiRuntime.load_from_environment()

        # Preserve the qualified application and OAuth checks, while deliberately
        # excluding the old Astra/Hermes product-key fingerprint requirement.
        credential_manifest = os.environ.get("TOOLATHLON_PI_CREDENTIAL_MANIFEST")
        self.credential_manifest_path = (
            Path(credential_manifest).resolve()
            if credential_manifest
            else self.freeze / "credential-manifest.json"
        )
        if (
            not self.credential_manifest_path.is_file()
            or self.credential_manifest_path.is_symlink()
        ):
            raise LifecycleError(
                f"Pi credential manifest is unavailable: {self.credential_manifest_path}"
            )
        manifest = read_json_object(self.credential_manifest_path)
        if (
            manifest.get("source_commit") != SOURCE_COMMIT
            or manifest.get("secret_values_recorded") is not False
            or manifest.get("toolathlon_application_credentials", {}).get("state")
            != "GO"
        ):
            raise LifecycleError("Pi credential manifest is not a qualified fingerprint set")
        records = manifest.get("toolathlon_application_credentials", {}).get("files")
        if not isinstance(records, list) or not records:
            raise LifecycleError("frozen application credential manifest is empty")
        mutable: list[str] = []
        for item in records:
            if not isinstance(item, dict):
                raise LifecycleError("invalid application credential record")
            relative = Path(str(item.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise LifecycleError("unsafe application credential path")
            path = self.source / relative
            if not path.is_file() or path.is_symlink():
                raise LifecycleError(f"application credential is unavailable: {path}")
            if is_runtime_mutable_credential_record(item):
                mutable.append(relative.as_posix())
            elif item.get("runtime_mutable") is True:
                raise LifecycleError(f"invalid mutable credential policy: {relative}")
            elif sha256_file(path) != item.get("sha256"):
                raise LifecycleError(f"application credential fingerprint drift: {path}")
        self.mutable_credential_paths = sorted(mutable)

    def _write_slot_config(self, gateway_port: int) -> Path:
        path = super()._write_slot_config(gateway_port)
        config = read_json_object(path)
        credential_manifest_path = getattr(self, "credential_manifest_path", None)
        if credential_manifest_path is not None:
            config["credential_manifest"] = str(credential_manifest_path)
            config["credential_manifest_scope"] = (
                "batch_runtime_rebaseline"
                if os.environ.get("TOOLATHLON_PI_CREDENTIAL_MANIFEST")
                else "frozen_m1"
            )
        permission_path = Path(str(config["run"]["permission_policy"]))
        permission = read_json_object(permission_path)
        permission["products"]["pi"] = {
            "mode": "external_lifecycle_boundary",
            "unresolved_action": "deny",
        }
        write_json_atomic(permission_path, permission, mode=0o600)
        config["benchmark_status"] = "exploratory_pi_only"
        config["run"]["system_id"] = "pi"
        config["evaluator"]["command"].append(
            "--evaluate_regardless_of_agent_status"
        )
        write_json_atomic(path, config, mode=0o600)
        return path

    def _finalize_pi(self) -> dict[str, Any]:
        assert self.lifecycle is not None
        required = (
            "resolved-config.json",
            "tool-schema-observed.json",
            "lifecycle-events.jsonl",
            "adapter-events.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "model-usage.jsonl",
            "resource-usage.jsonl",
            "evaluator/eval_res.json",
            "evaluator/eval.log",
            "failure-evidence.json",
            "run.json",
        )
        missing = [name for name in required if not (self.output / name).is_file()]
        if missing:
            raise LifecycleError(f"Pi run artifacts are missing: {missing}")
        run = read_json_object(self.output / "run.json")
        resolved = read_json_object(self.output / "resolved-config.json")
        if run.get("system_id") != "pi" or resolved.get("system_id") != "pi":
            raise LifecycleError("Pi artifact identity mismatch")
        if run.get("run_id") != self.args.run_id or run.get("task_id") != self.args.task_id:
            raise LifecycleError("Pi artifact run identity mismatch")
        for relative in (
            "lifecycle-events.jsonl",
            "adapter-events.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "model-usage.jsonl",
            "resource-usage.jsonl",
        ):
            for number, line in enumerate(
                (self.output / relative).read_text(encoding="utf-8").splitlines(), 1
            ):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LifecycleError(f"invalid JSONL {relative}:{number}") from exc
                if not isinstance(value, dict):
                    raise LifecycleError(f"non-object JSONL {relative}:{number}")
        self.lifecycle.append("artifact_validation.start")
        run["artifact_gate"] = {
            "status": "passed",
            "validator": "validate_pi_exploratory_artifacts",
            "validated_at": utc_now(),
        }
        write_json_atomic(self.output / "run.json", run, mode=0o644)
        self.lifecycle.append("artifact_validation.end", status="passed")
        manifest = self.output / "artifacts.sha256"
        candidates = [
            item
            for item in self.output.rglob("*")
            if item.is_file() and not item.is_symlink() and item != manifest
        ]
        write_sha256_manifest(manifest, candidates, root=self.output)
        return {
            "status": "passed",
            "benchmark_status": "exploratory_pi_only",
            "run_id": self.args.run_id,
            "task_id": self.args.task_id,
            "system_id": "pi",
            "artifact_count": len(candidates) + 1,
            "verify_status": run.get("verify_status"),
            "run_validity": run.get("run_validity"),
        }

    def execute(self) -> int:
        if self.output.exists() and any(self.output.iterdir()):
            raise LifecycleError("output directory must be absent or empty")
        self.output.mkdir(parents=True, exist_ok=True)
        self.lifecycle = JsonlEventWriter(
            self.output / "lifecycle-events.jsonl",
            run_id=self.args.run_id,
            system_id="pi",
        )
        self.private_dir = Path(tempfile.mkdtemp(prefix=f"toolathlon-{self.args.run_id}-"))
        os.chmod(self.private_dir, 0o700)
        sampler = ResourceSampler(
            self.output / "resource-usage.jsonl",
            run_id=self.args.run_id,
            system_id="pi",
            product_pid=lambda: self.product_pid[0],
            container_id=lambda: self.container_id[0],
            container_pid=lambda: self.container_pid[0],
        )
        sampler.start()
        slot_code = 2
        try:
            self.preflight()
            self._reset()
            self._start_container()
            self._copy_tree()
            self._preprocess()
            self._stash_private_artifacts()
            gateway_port = _free_port()
            self._start_gateway(gateway_port)
            config_path = self._write_slot_config(gateway_port)
            slot_code = run_pi_slot(
                config_path,
                before_evaluator=self._restore_for_evaluator,
                lifecycle_writer=self.lifecycle,
                resource_sampler=sampler,
                on_product_pid=lambda pid: self.product_pid.__setitem__(0, pid),
            )
        finally:
            try:
                self._cleanup()
            finally:
                sampler.close()
                if self.private_dir is not None:
                    shutil.rmtree(self.private_dir, ignore_errors=True)
                    self.private_dir = None
        validation = self._finalize_pi()
        print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
        return slot_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Toolathlon task with Pi 0.73.1")
    parser.add_argument("--task-id", default=QUALIFICATION_TASK)
    parser.add_argument("--experiment-id", default="toolathlon-pi-0.73.1-v1")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--replacement-for-run-id")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--toolathlon-source",
        type=Path,
        default=Path("/home/vagrant/dataset/Toolathlon"),
    )
    parser.add_argument("--docker-via-sudo", action="store_true")
    args = parser.parse_args(argv)
    args.system = "pi"
    args.run_id = _safe_id(args.run_id, "run_id")
    args.experiment_id = _safe_id(args.experiment_id, "experiment_id")
    args.task_id = _safe_id(args.task_id, "task_id")
    if args.replacement_for_run_id is not None:
        args.replacement_for_run_id = _safe_id(
            args.replacement_for_run_id, "replacement_for_run_id"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    return PiSingleTaskLifecycle(parse_args(argv)).execute()


if __name__ == "__main__":
    raise SystemExit(main())
