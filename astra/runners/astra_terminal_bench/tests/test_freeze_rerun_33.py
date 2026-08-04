import io
import json
import struct
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from astra.runners.astra_terminal_bench import freeze_rerun_33 as freeze


class FreezeRerun33Tests(unittest.TestCase):
    def setUp(self):
        self.root = freeze.workspace_root()
        self.task_list = (
            self.root
            / "astra"
            / "runners"
            / "astra_terminal_bench"
            / "rerun-from-scratch-33.tasks.txt"
        )
        self.tasks_dir = (
            self.root / "work" / "terminal-bench-2-1" / "tasks"
        )

    def test_checked_in_manifest_is_exact_and_resolves_to_task_configs(self):
        names = freeze.load_task_names(self.task_list)

        self.assertEqual(len(names), 33)
        self.assertEqual(len(set(names)), 33)
        for name in names:
            task_toml, config = freeze.load_task_config(self.tasks_dir / name)
            self.assertTrue(task_toml.is_file())
            self.assertEqual(config["task"]["name"], f"terminal-bench/{name}")
            self.assertTrue(freeze.image_from_task_config(name, config))

    def test_task_manifest_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.txt"
            path.write_text("\n".join(["same-task"] * 33), encoding="utf-8")

            with self.assertRaisesRegex(freeze.FreezeError, "duplicate"):
                freeze.load_task_names(path)

    def test_resolved_per_task_timeouts_are_frozen(self):
        tasks = freeze.prepare_tasks(
            self.tasks_dir,
            ["regex-log"],
            product_timeout_multiplier=2.25,
            harbor_agent_timeout_multiplier=2.5,
            harbor_verifier_timeout_multiplier=2.0,
            harbor_agent_setup_timeout_multiplier=2.0,
            harbor_environment_build_timeout_multiplier=2.0,
            harbor_agent_setup_base_timeout_sec=360,
        )

        self.assertEqual(
            tasks[0]["timeouts"],
            {
                "upstream_agent_timeout_sec": 900.0,
                "product_timeout_multiplier": 2.25,
                "product_timeout_sec": 2025.0,
                "harbor_agent_timeout_multiplier": 2.5,
                "harbor_agent_timeout_sec": 2250.0,
                "upstream_verifier_timeout_sec": 900.0,
                "harbor_verifier_timeout_multiplier": 2.0,
                "harbor_verifier_timeout_sec": 1800.0,
                "upstream_environment_build_timeout_sec": 600.0,
                "harbor_environment_build_timeout_multiplier": 2.0,
                "harbor_environment_build_timeout_sec": 1200.0,
                "harbor_agent_setup_base_timeout_sec": 360,
                "harbor_agent_setup_timeout_multiplier": 2.0,
                "harbor_agent_setup_timeout_sec": 720.0,
            },
        )

    def test_elf_arch_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for machine, expected in ((62, "amd64"), (183, "arm64")):
                path = root / expected
                header = bytearray(20)
                header[:4] = b"\x7fELF"
                header[5] = 1
                header[18:20] = struct.pack("<H", machine)
                path.write_bytes(header)

                self.assertEqual(freeze.detect_elf_arch(path), expected)

    def test_pull_retries_are_bounded_and_exponential(self):
        results = [
            subprocess.CompletedProcess([], 1, "", "first"),
            subprocess.CompletedProcess([], 1, "", "second"),
            subprocess.CompletedProcess([], 0, "ok", ""),
        ]
        delays = []

        with mock.patch.object(
            freeze, "run_command", side_effect=results
        ) as run:
            report = freeze.pull_image_with_retry(
                "docker",
                "example/image:tag",
                attempts=5,
                base_delay_sec=2,
                max_delay_sec=30,
                jitter_sec=1,
                sleep_fn=delays.append,
                random_fn=lambda _start, _end: 0.25,
            )

        self.assertEqual(run.call_count, 3)
        self.assertEqual(delays, [2.25, 4.25])
        self.assertEqual(report["attempts"], 3)

    def test_inspect_freezes_digest_architecture_and_working_directory(self):
        inspect_result = subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": "sha256:image-id",
                        "RepoDigests": [
                            "example/image@sha256:manifest-digest"
                        ],
                        "Os": "linux",
                        "Architecture": "aarch64",
                        "Config": {
                            "WorkingDir": "/workspace",
                            "User": "1000",
                            "Entrypoint": None,
                            "Cmd": ["/bin/sh"],
                        },
                    }
                ]
            ),
            "",
        )
        with mock.patch.object(
            freeze, "run_command", return_value=inspect_result
        ):
            metadata = freeze.inspect_image("docker", "example/image:tag")

        self.assertEqual(metadata["architecture"], "arm64")
        self.assertEqual(metadata["working_dir"], "/workspace")
        self.assertEqual(
            metadata["frozen_ref"],
            "example/image@sha256:manifest-digest",
        )

    def test_write_manifest_is_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frozen.json"
            freeze.write_manifest_once(output, {"value": 1})

            with self.assertRaisesRegex(freeze.FreezeError, "overwrite"):
                freeze.write_manifest_once(output, {"value": 2})

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {"value": 1},
            )

    def test_model_freeze_metadata_rejects_wrong_id_or_secrets(self):
        expected_id = freeze.DEFAULT_MODEL
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_text(
                json.dumps(
                    {
                        "model": {"model_id": expected_id},
                        "secrets_included": False,
                    }
                ),
                encoding="utf-8",
            )
            metadata = freeze.model_freeze_metadata(path, expected_id)
            self.assertEqual(metadata["model_id"], expected_id)
            self.assertFalse(metadata["secrets_included"])

            path.write_text(
                json.dumps(
                    {
                        "model": {"model_id": "wrong-model"},
                        "secrets_included": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(freeze.FreezeError, "model ID mismatch"):
                freeze.model_freeze_metadata(path, expected_id)

            path.write_text(
                json.dumps(
                    {
                        "model": {"model_id": expected_id},
                        "secrets_included": True,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(freeze.FreezeError, "secrets_included"):
                freeze.model_freeze_metadata(path, expected_id)

    def test_dry_run_does_not_call_docker(self):
        with (
            mock.patch.object(
                freeze, "docker_server_metadata"
            ) as docker_metadata,
            mock.patch.object(freeze, "inspect_image") as inspect_image,
            mock.patch.object(freeze, "pull_image_with_retry") as pull_image,
            redirect_stdout(io.StringIO()) as output,
        ):
            return_code = freeze.main(["--dry-run"])

        self.assertEqual(return_code, 0)
        docker_metadata.assert_not_called()
        inspect_image.assert_not_called()
        pull_image.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["task_count"], 33)

    def test_default_runner_files_freeze_host_gateway_overlay(self):
        overlay = (
            self.root
            / "astra"
            / "runners"
            / "astra_terminal_bench"
            / "host-docker-internal.compose.yaml"
        ).resolve()

        self.assertIn(
            overlay,
            [path.resolve() for path in freeze.default_runner_files(
                self.root, self.task_list
            )],
        )
        self.assertIn(
            "host.docker.internal:host-gateway",
            overlay.read_text(encoding="utf-8"),
        )
        model_freeze = (
            self.root
            / "astra"
            / "runners"
            / "astra_terminal_bench"
            / "model-c5bde5de.freeze.json"
        ).resolve()
        self.assertIn(
            model_freeze,
            [path.resolve() for path in freeze.default_runner_files(
                self.root, self.task_list
            )],
        )

    def test_frozen_budget_and_permission_policy(self):
        args = SimpleNamespace(
            docker_bin="docker",
            pull_attempts=5,
            pull_base_delay_sec=2.0,
            pull_max_delay_sec=30.0,
            pull_jitter_sec=1.0,
            version_probe_timeout_sec=30.0,
            task_list=self.task_list,
            tasks_dir=self.tasks_dir,
            model=freeze.DEFAULT_MODEL,
            max_turns=50,
            fallback_timeout_sec=600,
            llm_total_budget_sec=900,
            stream_transport_retries=2,
            optional_retry_min_remaining_sec=930,
            product_timeout_multiplier=2.25,
            timeout_multiplier=2.0,
            agent_timeout_multiplier=2.5,
            verifier_timeout_multiplier=2.0,
            agent_setup_timeout_multiplier=2.0,
            environment_build_timeout_multiplier=2.0,
            agent_setup_base_timeout_sec=360,
        )
        image = {
            "configured_ref": "example/image:tag",
            "image_id": "sha256:image",
            "repo_digests": ["example/image@sha256:digest"],
            "frozen_ref": "example/image@sha256:digest",
            "os": "linux",
            "architecture": "amd64",
            "working_dir": "/app",
            "effective_working_dir": "/app",
        }
        task = {
            "name": "tune-mjcf",
            "configured_image": "example/image:tag",
        }
        artifacts = {
            "amd64": {
                "path": "/tmp/astra",
                "sha256": "artifact-sha",
                "architecture": "amd64",
            },
            "arm64": {
                "path": "/tmp/astra-arm64",
                "sha256": "arm-artifact-sha",
                "architecture": "arm64",
            },
        }
        model_freeze = {
            "path": "/tmp/model-freeze.json",
            "sha256": "model-freeze-sha",
            "size_bytes": 123,
            "model_id": freeze.DEFAULT_MODEL,
            "secrets_included": False,
        }
        with (
            mock.patch.object(freeze, "inspect_image", return_value=image),
            mock.patch.object(
                freeze,
                "probe_astra_version",
                return_value={"returncode": 0, "output": "astra"},
            ),
            mock.patch.object(freeze, "git_revision", return_value=None),
        ):
            manifest = freeze.freeze_manifest(
                args,
                names=["tune-mjcf"],
                tasks=[task],
                artifacts=artifacts,
                astra_server={
                    "path": "/tmp/astra-server",
                    "sha256": "server-sha",
                },
                model_freeze=model_freeze,
                runner_files=[],
                docker_metadata={"architecture": "arm64"},
                pull_images=False,
            )

        self.assertEqual(
            manifest["execution"]["permissions"],
            {"permission_mode": "auto", "read_memory": False},
        )
        self.assertEqual(
            manifest["execution"]["model_freeze"],
            model_freeze,
        )
        self.assertEqual(
            manifest["execution"]["environment"],
            {
                "type": "docker",
                "force_build": False,
                "delete": True,
                "extra_allowed_hosts": ["host.docker.internal"],
                "extra_docker_compose": [
                    str(
                        (
                            self.root
                            / "astra"
                            / "runners"
                            / "astra_terminal_bench"
                            / "host-docker-internal.compose.yaml"
                        ).resolve()
                    )
                ],
            },
        )
        self.assertEqual(
            manifest["execution"]["budgets"],
            {
                "llm_fallback_timeout_sec": 600,
                "llm_total_budget_sec": 900,
                "stream_transport_retries": 2,
                "retry_policy": {
                    "first_retry_guaranteed": True,
                    "additional_retries_require_remaining_budget": True,
                    "optional_retry_min_remaining_seconds": 930,
                },
                "product_timeout_multiplier": 2.25,
                "harbor_timeout_multipliers": {
                    "timeout_multiplier": 2.0,
                    "agent_timeout_multiplier": 2.5,
                    "verifier_timeout_multiplier": 2.0,
                    "agent_setup_timeout_multiplier": 2.0,
                    "environment_build_timeout_multiplier": 2.0,
                },
            },
        )
        self.assertFalse(
            manifest["preflight"][
                "ready_to_run_all_tasks_on_this_docker_server"
            ]
        )
        self.assertEqual(
            manifest["preflight"]["blockers"][0]["task"],
            "tune-mjcf",
        )
        self.assertEqual(manifest["queues_by_architecture"]["amd64"], [])
        self.assertEqual(
            manifest["queues_by_architecture"]["native_amd64_required"],
            ["tune-mjcf"],
        )


if __name__ == "__main__":
    unittest.main()
