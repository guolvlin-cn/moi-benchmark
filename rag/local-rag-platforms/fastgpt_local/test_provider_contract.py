#!/usr/bin/env python3
"""Offline regression checks for the FastGPT -> AIProxy channel contract."""

import json
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load_fastgpt_module():
    spec = importlib.util.spec_from_file_location("fastgpt_local", HERE / "fastgpt_local.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProviderContractTest(unittest.TestCase):
    def test_channel_contract_is_complete(self) -> None:
        contract = json.loads((HERE / "contracts.json").read_text(encoding="utf-8"))
        channel = contract["provider_channel_api"]

        self.assertEqual(channel["fastgpt_proxy_base"], "/api/aiproxy/api")
        self.assertEqual(channel["create"]["fastgpt_path"], "/api/aiproxy/api/createChannel")
        self.assertEqual(channel["list"]["fastgpt_path"], "/api/aiproxy/api/channels/all")
        self.assertEqual(channel["test"]["fastgpt_path"], "/api/core/ai/model/test")
        self.assertEqual(channel["test"]["fastgpt_method"], "GET")
        self.assertEqual(channel["test"]["fastgpt_query"], ["model", "channelId"])
        self.assertEqual(channel["create"]["aiproxy_path"], "/api/channel/")
        self.assertEqual(channel["list"]["aiproxy_path"], "/api/channels/all")
        self.assertEqual(channel["test"]["aiproxy_saved_path"], "/api/channel/{id}/test")
        self.assertEqual(channel["authentication"]["fastgpt_proxy"], "root browser session")
        self.assertEqual(channel["authentication"]["aiproxy_direct"], "Authorization: Bearer ${AIPROXY_ADMIN_KEY}")

        payload = channel["create"]["payload"]
        self.assertEqual(payload["type"], 1)
        self.assertEqual(payload["models"], ["qwen3.6-flash", "bge-m3"])
        self.assertEqual(payload["priority"], 1)
        self.assertNotIn("status", payload)

    def test_qianfan_profile_is_independent_from_taas(self) -> None:
        module_path = HERE / "fastgpt_local.py"
        spec = importlib.util.spec_from_file_location("fastgpt_local_module", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        qianfan = module.PROVIDER_PROFILES["qianfan"]
        taas = module.PROVIDER_PROFILES["taas"]
        self.assertEqual(qianfan["base_url"], "https://qianfan.baidubce.com/v2")
        self.assertEqual(qianfan["llm_model"], "deepseek-v4-flash")
        self.assertEqual(qianfan["embedding_model"], "qwen3-embedding-8b")
        self.assertEqual(qianfan["reranker_model"], "qwen3-reranker-8b")
        self.assertNotEqual(qianfan["env_prefix"], taas["env_prefix"])

    def test_native_failure_still_writes_unified_artifact(self) -> None:
        module = load_fastgpt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fixtures"
            source.mkdir()
            (source / "one.md").write_text("smoke", encoding="utf-8")
            module.ROOT = root
            module.RUNTIME = root / ".local-services/fastgpt_local"
            responses = [
                "dataset-1",
                {"collectionId": "collection-1"},
                {"list": [{"trainingAmount": 0, "activeTrainingAmount": 0, "finalErrorAmount": 0}]},
                {"list": [{"sourceName": "one.md"}]},
                module.ContractError("native request timed out after 60s"),
            ]

            def fake_request(*_args, **_kwargs):
                response = responses.pop(0)
                if isinstance(response, Exception):
                    raise response
                return response

            env = {
                "FASTGPT_BASE_URL": "http://127.0.0.1:3000",
                "FASTGPT_API_KEY": "test-local-key",
                "FASTGPT_APP_ID": "test-app",
                "FASTGPT_SMOKE_SOURCE_DIR": "fixtures",
            }
            with patch.dict(os.environ, env, clear=False), patch.object(module, "api_request", side_effect=fake_request):
                self.assertEqual(module.smoke(SimpleNamespace(execute=True)), 1)

            artifacts = list((module.RUNTIME / "logs").glob("*/smoke-result.json"))
            self.assertEqual(len(artifacts), 1)
            result = json.loads(artifacts[0].read_text(encoding="utf-8"))
            self.assertEqual(result["service_status"], "ready")
            self.assertEqual(result["ingest_status"], "ready")
            self.assertEqual(result["retrieval_status"], "success")
            self.assertEqual(result["native_status"], "error")
            self.assertEqual(result["blocked_reason"], "NATIVE_SMOKE_TIMEOUT")
            self.assertTrue(artifacts[0].with_suffix(".json.sha256").exists())


if __name__ == "__main__":
    unittest.main()
