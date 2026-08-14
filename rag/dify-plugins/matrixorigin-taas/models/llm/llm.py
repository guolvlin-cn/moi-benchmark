from __future__ import annotations

from collections.abc import Generator
from typing import Optional

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


class MatrixOriginTaaSLargeLanguageModel(OAICompatLargeLanguageModel):
    """Use the SDK's OpenAI-compatible chat implementation with TaaS credentials."""

    @staticmethod
    def _oai_credentials(model: str, credentials: dict) -> dict:
        mapped = dict(credentials)
        mapped.update(
            {
                "endpoint_url": str(credentials.get("base_url") or "").rstrip("/"),
                "endpoint_model_name": model,
                "mode": "chat",
                "stream_mode_auth": "not_use",
                "function_calling_type": "no_call",
                "stream_function_calling": "not_supported",
                "vision_support": "not_support",
            }
        )
        return mapped

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> LLMResult | Generator[LLMResultChunk, None, None]:
        return super()._invoke(
            model=model,
            credentials=self._oai_credentials(model, credentials),
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        super().validate_credentials(model, self._oai_credentials(model, credentials))

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        return super().get_num_tokens(
            model,
            self._oai_credentials(model, credentials),
            prompt_messages,
            tools,
        )
