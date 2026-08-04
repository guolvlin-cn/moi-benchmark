from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().with_name("pipeline.py")


class PipelineCLITest(unittest.TestCase):
    def test_precision_pipeline_passes_parser_mode_and_loads_shared_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_file = root / "sample.pdf"
            input_file.write_bytes(b"fake pdf")
            config = root / "config.json"
            config.write_text("{}\n", encoding="utf-8")
            env_file = root / ".env"
            env_file.write_text(
                "MINERU_API_TOKEN=fake-mineru-token\nTAAS_API_KEY=fake-taas-token\n",
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_go = fake_bin / "go"
            fake_go.write_text(FAKE_GO, encoding="utf-8")
            fake_go.chmod(0o700)
            invocation_log = root / "go-invocations.jsonl"
            environment = os.environ.copy()
            environment.pop("MINERU_API_TOKEN", None)
            environment.pop("TAAS_API_KEY", None)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
            environment["FAKE_GO_LOG"] = str(invocation_log)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE),
                    "--input",
                    str(input_file),
                    "--config",
                    str(config),
                    "--parser-pipeline",
                    "precision",
                    "--env-file",
                    str(env_file),
                    "--run",
                    str(root / "runs"),
                ],
                cwd=PIPELINE.parent,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            invocations = [json.loads(line) for line in invocation_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(invocations), 2)
            parser_invocation = invocations[0]
            self.assertIn("--pipeline", parser_invocation["args"])
            self.assertEqual(
                parser_invocation["args"][parser_invocation["args"].index("--pipeline") + 1],
                "precision",
            )
            self.assertEqual(
                parser_invocation["args"][parser_invocation["args"].index("--env-file") + 1],
                str(env_file.resolve()),
            )
            for invocation in invocations:
                self.assertEqual(invocation["mineru_token"], "fake-mineru-token")
                self.assertEqual(invocation["taas_key"], "fake-taas-token")


FAKE_GO = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_GO_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps({
        "args": args,
        "mineru_token": os.environ.get("MINERU_API_TOKEN"),
        "taas_key": os.environ.get("TAAS_API_KEY"),
    }) + "\n")

run_root = Path(args[args.index("--run") + 1])
child = run_root / "fake-child"
child.mkdir(parents=True, exist_ok=True)
if "./cmd/local-matrixflow-parser" in args:
    (child / "documents.jsonl").write_text(
        '{"content":"parsed","type":"text","metadata":{"file_id":"fake","file_name":"sample.pdf"}}\n',
        encoding="utf-8",
    )
    (child / "summary.json").write_text('{"documents":1}\n', encoding="utf-8")
else:
    (child / "ingest-state.json").write_text('{}\n', encoding="utf-8")
print(f"run_dir={child}")
'''


if __name__ == "__main__":
    unittest.main()
