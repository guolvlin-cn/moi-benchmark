import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module():
    spec = importlib.util.spec_from_file_location("rag_api_console", HERE / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EnvStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_module()

    def test_write_env_preserves_unmanaged_and_does_not_clear_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.env"
            path.write_text('UNMANAGED="keep"\nAPI_KEY="old"\n', encoding="utf-8")
            path.chmod(0o644)
            self.app.write_env(path, {"API_KEY": "", "APP_ID": "new"}, {"API_KEY", "APP_ID"})
            _, values = self.app.parse_env(path)
            self.assertEqual(values["UNMANAGED"], "keep")
            self.assertEqual(values["API_KEY"], "old")
            self.assertEqual(values["APP_ID"], "new")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_platform_payload_never_returns_secret_value(self):
        platform = self.app.PLATFORMS["dify_local"]
        original = platform.config_file
        with tempfile.TemporaryDirectory() as tmp:
            replacement = self.app.Platform(**{**platform.__dict__, "config_file": Path(tmp) / "credentials.env"})
            replacement.config_file.write_text('DIFY_LOCAL_API_KEY="top-secret"\n', encoding="utf-8")
            payload = self.app.platform_payload(replacement, [], include_probe=False)
            field = next(item for item in payload["fields"] if item["key"] == "DIFY_LOCAL_API_KEY")
            self.assertTrue(field["configured"])
            self.assertEqual(field["value"], "")
            self.assertNotIn("top-secret", repr(payload))

    def test_moi_requires_both_runtime_containers(self):
        platform = self.app.PLATFORMS["moi_local"]
        matrixone = {"Names": "matrixone", "State": "running"}
        parser = {"Names": "moi-openxml-parser", "State": "running"}
        self.assertFalse(self.app.is_running(platform, [matrixone]))
        self.assertTrue(self.app.is_running(platform, [matrixone, parser]))

    def test_moi_is_exempt_from_competitor_serial_policy(self):
        self.assertTrue(self.app.PLATFORMS["moi_local"].serial_exempt)
        self.assertFalse(self.app.PLATFORMS["fastgpt_local"].serial_exempt)


if __name__ == "__main__":
    unittest.main()
