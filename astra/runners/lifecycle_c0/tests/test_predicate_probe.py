import tempfile
import unittest
from pathlib import Path

from astra.runners.lifecycle_c0.predicate_probe import (
    OVERFULL_INPUT_INITIAL_SHA256,
    observe,
)


class PredicateProbeTests(unittest.TestCase):
    def test_generic_product_live_predicate_is_stable_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            matched, evidence = observe(
                "terminal-bench.generic.product-live",
                workspace=workspace,
            )
            self.assertTrue(matched)
            self.assertEqual(evidence, {"state": "product_live"})
            self.assertEqual(list(workspace.iterdir()), [])

    def test_modernize_matches_only_partial_required_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            predicate = (
                "terminal-bench.modernize-scientific-stack.partial-outputs"
            )
            self.assertFalse(observe(predicate, workspace=workspace)[0])
            (workspace / "requirements.txt").write_text("pandas>=2\n")
            self.assertTrue(observe(predicate, workspace=workspace)[0])
            (workspace / "analyze_climate_modern.py").write_text("print('ok')\n")
            self.assertFalse(observe(predicate, workspace=workspace)[0])

    def test_overfull_matches_changed_input_before_clean_log(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            predicate = (
                "terminal-bench.overfull-hbox.changed-input-before-clean-log"
            )
            (workspace / "input.tex").write_text(OVERFULL_INPUT_INITIAL_SHA256)
            self.assertTrue(observe(predicate, workspace=workspace)[0])
            (workspace / "main.log").write_text("Overfull \\hbox\n")
            self.assertTrue(observe(predicate, workspace=workspace)[0])
            (workspace / "main.log").write_text("clean\n")
            self.assertFalse(observe(predicate, workspace=workspace)[0])

    def test_pmars_matches_ready_source_before_binary_install(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "app"
            binary = Path(directory) / "usr" / "local" / "bin" / "pmars"
            source = workspace / "pmars-1.2"
            (source / "debian").mkdir(parents=True)
            (source / "src").mkdir()
            (source / "debian" / "changelog").write_text("pmars (1.2)\n")
            (source / "src" / "Makefile").write_text("all:\n")
            predicate = "terminal-bench.build-pmars.source-before-install"
            self.assertTrue(
                observe(
                    predicate, workspace=workspace, pmars_binary=binary
                )[0]
            )
            binary.parent.mkdir(parents=True)
            binary.write_text("installed")
            self.assertFalse(
                observe(
                    predicate, workspace=workspace, pmars_binary=binary
                )[0]
            )

    def test_db_wal_matches_valid_magic_before_recovered_output(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            predicate = (
                "terminal-bench.db-wal-recovery.valid-wal-before-output"
            )
            (workspace / "main.db-wal").write_bytes(b"\x37\x7f\x06\x82payload")
            self.assertTrue(observe(predicate, workspace=workspace)[0])
            (workspace / "recovered.json").write_text("[]")
            self.assertFalse(observe(predicate, workspace=workspace)[0])

    def test_predicates_do_not_follow_workspace_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "app"
            workspace.mkdir()
            outside = root / "outside-input.tex"
            outside.write_text("changed")
            (workspace / "input.tex").symlink_to(outside)
            predicate = (
                "terminal-bench.overfull-hbox.changed-input-before-clean-log"
            )
            matched, evidence = observe(predicate, workspace=workspace)
            self.assertFalse(matched)
            self.assertEqual(evidence["input_state"], "missing_or_unstable")


if __name__ == "__main__":
    unittest.main()
