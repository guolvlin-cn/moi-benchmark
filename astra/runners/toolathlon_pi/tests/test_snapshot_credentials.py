from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from astra.runners.toolathlon_pi.scripts.snapshot_application_credentials import main


class SnapshotApplicationCredentialsTests(unittest.TestCase):
    def test_snapshot_updates_fingerprints_without_copying_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            credential = source / "configs" / "service-token.txt"
            credential.parent.mkdir(parents=True)
            credential.write_text("secret-value\n", encoding="utf-8")
            base = root / "base.json"
            base.write_text(
                json.dumps(
                    {
                        "secret_values_recorded": False,
                        "toolathlon_application_credentials": {
                            "state": "GO",
                            "files": [
                                {
                                    "path": "configs/service-token.txt",
                                    "sha256": "0" * 64,
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = root / "runtime.json"

            with patch.object(
                sys,
                "argv",
                [
                    "snapshot_application_credentials.py",
                    "--base",
                    str(base),
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(main(), 0)

            serialized = output.read_text(encoding="utf-8")
            record = json.loads(serialized)
            item = record["toolathlon_application_credentials"]["files"][0]
            self.assertNotIn("secret-value", serialized)
            self.assertEqual(
                item["sha256"],
                hashlib.sha256(credential.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                record["runtime_rebaseline"]["scope"],
                "application credential file fingerprints only",
            )


if __name__ == "__main__":
    unittest.main()
