import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).with_name("run_stage1.py")


class Stage1AdapterCLITest(unittest.TestCase):
    def test_prepare_creates_deterministic_official_subset_and_single_page_pdfs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            images = root / "images"
            images.mkdir()
            records = []
            for index, source in enumerate(("book", "book", "newspaper", "PPT2PDF")):
                image_name = f"page-{index}.png"
                Image.new("RGB", (40 + index, 30 + index), color=(index * 20, 10, 30)).save(images / image_name)
                records.append(
                    {
                        "layout_dets": [],
                        "page_info": {
                            "page_no": index,
                            "height": 30 + index,
                            "width": 40 + index,
                            "image_path": image_name,
                            "page_attribute": {
                                "data_source": source,
                                "language": "english" if index % 2 == 0 else "simplified_chinese",
                                "layout": "single_column",
                            },
                        },
                    }
                )
            ground_truth = root / "OmniDocBench.json"
            ground_truth.write_text(json.dumps(records), encoding="utf-8")

            selected_runs = []
            for run_name in ("run-a", "run-b"):
                run_dir = root / run_name
                command = [
                    sys.executable,
                    str(SCRIPT),
                    "prepare",
                    "--ground-truth",
                    str(ground_truth),
                    "--images",
                    str(images),
                    "--run-dir",
                    str(run_dir),
                    "--sample-size",
                    "3",
                    "--seed",
                    "17",
                ]
                completed = subprocess.run(command, text=True, capture_output=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                subset = json.loads((run_dir / "official" / "ground-truth.json").read_text())
                selected = [record["page_info"]["image_path"] for record in subset]
                selected_runs.append(selected)
                self.assertEqual(len(subset), 3)
                self.assertEqual(len(list((run_dir / "artifacts" / "inputs").glob("*.pdf"))), 3)
                self.assertEqual(len((run_dir / "artifacts" / "sample-manifest.jsonl").read_text().splitlines()), 3)

            self.assertEqual(selected_runs[0], selected_runs[1])
            self.assertGreaterEqual(len({records[int(name.removeprefix("page-").removesuffix(".png"))]["page_info"]["page_attribute"]["data_source"] for name in selected_runs[0]}), 2)

    def test_parse_exports_official_markdown_and_attempt_ledger(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "run"
            input_pdf = run_dir / "artifacts" / "inputs" / "page-1.pdf"
            input_pdf.parent.mkdir(parents=True)
            input_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            manifest = run_dir / "artifacts" / "sample-manifest.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "page_id": "page-1",
                        "input_pdf": str(input_pdf),
                        "prediction": str(run_dir / "official" / "predictions" / "page-1.md"),
                    }
                )
                + "\n"
            )
            fake_parser = root / "fake-parser.py"
            fake_parser.write_text(
                """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv
run_root = pathlib.Path(args[args.index('--run') + 1])
child = run_root / 'fixed'
(child / 'product-artifacts').mkdir(parents=True, exist_ok=True)
(child / 'product-artifacts' / 'mineru-full.md').write_text('# parsed page\\n')
(child / 'summary.json').write_text('{\"duration_ms\": 12.5, \"documents\": 1}')
print(f'run_dir={child}')
"""
            )
            fake_parser.chmod(0o755)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "parse",
                    "--run-dir",
                    str(run_dir),
                    "--parser-bin",
                    str(fake_parser),
                    "--pipeline",
                    "precision",
                    "--workers",
                    "1",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                (run_dir / "official" / "predictions" / "page-1.md").read_text(),
                "# parsed page\n",
            )
            attempts = [json.loads(line) for line in (run_dir / "moi-unified" / "attempts.jsonl").read_text().splitlines()]
            self.assertEqual(attempts[0]["status"], "ok")
            self.assertEqual(attempts[0]["pipeline"], "precision")

            verified = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "verify",
                    "--run-dir",
                    str(run_dir),
                    "--pipeline",
                    "precision",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            report = json.loads((run_dir / "moi-unified" / "verification.json").read_text())
            self.assertTrue(report["complete"])
            self.assertEqual(report["prediction_files"], 1)

    def test_verify_rejects_an_incomplete_parse(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            prediction = run_dir / "official" / "predictions" / "page-1.md"
            (run_dir / "artifacts" / "sample-manifest.jsonl").write_text(
                json.dumps({"page_id": "page-1", "prediction": str(prediction)}) + "\n"
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "verify",
                    "--run-dir",
                    str(run_dir),
                    "--pipeline",
                    "precision",
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            report = json.loads((run_dir / "moi-unified" / "verification.json").read_text())
            self.assertFalse(report["complete"])
            self.assertIn("missing attempts: 1", report["issues"])

    def test_handoff_blocks_automatic_parse_of_remaining_pages(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            (run_dir / "artifacts" / "sample-manifest.jsonl").write_text(
                json.dumps(
                    {
                        "page_id": "page-1",
                        "input_pdf": str(run_dir / "page-1.pdf"),
                        "prediction": str(run_dir / "official" / "predictions" / "page-1.md"),
                    }
                )
                + "\n"
            )
            (run_dir / "PRECISION-HANDOFF.md").write_text("externally owned\n")
            parser = root / "must-not-run"
            parser.write_text("#!/bin/sh\nexit 99\n")
            parser.chmod(0o755)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "parse",
                    "--run-dir",
                    str(run_dir),
                    "--parser-bin",
                    str(parser),
                    "--pipeline",
                    "precision",
                    "--workers",
                    "1",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("automatic_parse_blocked=true", completed.stdout)

    def test_reuse_copies_only_overlapping_successful_predictions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            (source / "official" / "predictions").mkdir(parents=True)
            (source / "moi-unified").mkdir(parents=True)
            (target / "artifacts").mkdir(parents=True)
            (source / "official" / "predictions" / "page-1.md").write_text("reused markdown")
            (source / "moi-unified" / "attempts.jsonl").write_text(
                json.dumps({"page_id": "page-1", "pipeline": "precision", "status": "ok", "latency_ms": 10}) + "\n"
            )
            (target / "artifacts" / "sample-manifest.jsonl").write_text(
                "\n".join(
                    json.dumps({"page_id": page_id, "prediction": str(target / "official" / "predictions" / f"{page_id}.md")})
                    for page_id in ("page-1", "page-2")
                )
                + "\n"
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "reuse",
                    "--run-dir",
                    str(target),
                    "--source-run",
                    str(source),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((target / "official" / "predictions" / "page-1.md").read_text(), "reused markdown")
            self.assertFalse((target / "official" / "predictions" / "page-2.md").exists())
            reused = json.loads((target / "moi-unified" / "attempts.jsonl").read_text().strip())
            self.assertTrue(reused["reused"])
            self.assertEqual(reused["reused_from"], str(source.resolve()))


if __name__ == "__main__":
    unittest.main()
