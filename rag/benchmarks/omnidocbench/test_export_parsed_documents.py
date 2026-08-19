import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("export_parsed_documents.py")
SPEC = importlib.util.spec_from_file_location("export_parsed_documents", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExportParsedDocumentsTest(unittest.TestCase):
    def test_export_run_separates_engine_and_pipeline_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "source-run"
            input_pdf = run_dir / "artifacts" / "inputs" / "page-1.pdf"
            prediction = run_dir / "official" / "predictions" / "page-1.md"
            parser_run = run_dir / "artifacts" / "parser-runs" / "precision" / "fixed"
            input_pdf.parent.mkdir(parents=True)
            prediction.parent.mkdir(parents=True)
            (parser_run / "product-artifacts").mkdir(parents=True)
            input_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            prediction.write_text("# parsed\n", encoding="utf-8")
            (parser_run / "result.json").write_text('{"status":"ok"}\n', encoding="utf-8")
            (parser_run / "summary.json").write_text('{"documents":1}\n', encoding="utf-8")

            sample_manifest = run_dir / "artifacts" / "sample-manifest.jsonl"
            sample_manifest.write_text(
                json.dumps({"page_id": "page 1/unsafe", "input_pdf": str(input_pdf)}) + "\n",
                encoding="utf-8",
            )
            attempts = run_dir / "moi-unified" / "attempts.jsonl"
            attempts.parent.mkdir(parents=True)
            attempts.write_text(
                json.dumps(
                    {
                        "page_id": "page 1/unsafe",
                        "pipeline": "precision",
                        "status": "ok",
                        "prediction": str(prediction),
                        "parser_run_dir": str(parser_run),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output_root = root / "exports"
            first = MODULE.export_run(run_dir, output_root, "mineru", "precision")
            second = MODULE.export_run(run_dir, output_root, "mineru", "precision")
            self.assertEqual(first, second)
            manifest_row = json.loads(
                (output_root / "mineru" / "precision" / "source-run" / "export-manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(manifest_row["page_id"], "page 1/unsafe")
            self.assertNotIn("/", manifest_row["directory_id"])
            document_dir = (
                output_root
                / "mineru"
                / "precision"
                / "source-run"
                / "documents"
                / manifest_row["directory_id"]
            )
            self.assertEqual((document_dir / "input.pdf").read_bytes(), input_pdf.read_bytes())
            self.assertEqual((document_dir / "parsed.md").read_text(encoding="utf-8"), "# parsed\n")
            self.assertTrue((document_dir / "parser-result.json").is_file())
            self.assertTrue((document_dir / "parser-summary.json").is_file())

    def test_export_run_rejects_unsafe_path_components(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaisesRegex(ValueError, "safe path component"):
                MODULE.export_run(root / "run", root / "exports", "../moi", "native")


if __name__ == "__main__":
    unittest.main()
