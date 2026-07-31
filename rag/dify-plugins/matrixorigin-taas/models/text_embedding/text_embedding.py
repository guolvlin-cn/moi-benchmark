from __future__ import annotations

import time
from typing import Optional

from dify_plugin import TextEmbeddingModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    PriceType,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalEmbeddingResult,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.shared import multimodal_content, post_json


class MatrixOriginTaaSTextEmbeddingModel(TextEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        embeddings: list[list[float]] = []
        total_tokens = 0

        # TaaS currently returns one qwen3-vl embedding per request even when
        # multiple inputs are supplied, so invoke sequentially for stable
        # one-input/one-output cardinality. The same path also works for bge-m3.
        for text in texts:
            response = post_json(
                credentials,
                "/embeddings",
                {
                    "model": model,
                    "input": [text],
                    "encoding_format": "float",
                },
            )
            embedding, tokens = self._parse_embedding(response)
            embeddings.append(embedding)
            total_tokens += tokens

        return TextEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._usage(model, credentials, total_tokens),
        )

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> MultiModalEmbeddingResult:
        embeddings: list[list[float]] = []
        total_tokens = 0

        for document in documents:
            response = post_json(
                credentials,
                "/embeddings",
                {
                    "model": model,
                    "input": [multimodal_content(document)],
                    "encoding_format": "float",
                },
            )
            embedding, tokens = self._parse_embedding(response)
            embeddings.append(embedding)
            total_tokens += tokens

        return MultiModalEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._usage(model, credentials, total_tokens),
        )

    @staticmethod
    def _parse_embedding(response: dict) -> tuple[list[float], int]:
        data = response.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError(
                f"TaaS embedding response must contain exactly one result, got {len(data or [])}"
            )
        vector = data[0].get("embedding")
        if not isinstance(vector, list) or not vector:
            raise ValueError("TaaS embedding response is missing data[0].embedding")
        usage = response.get("usage") or {}
        tokens = int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
        return [float(value) for value in vector], tokens

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        return [self._get_num_tokens_by_gpt2(text) for text in texts]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as exc:
            raise CredentialsValidateFailedError(str(exc)) from exc

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError, KeyError, TypeError, ValueError],
        }

    def _usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        price = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )
        return EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=price.unit_price,
            price_unit=price.unit,
            total_price=price.total_amount,
            currency=price.currency,
            latency=time.perf_counter() - self.started_at,
        )

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        features = []
        if credentials.get("vision_support") == "support":
            features.append(ModelFeature.VISION)
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.TEXT_EMBEDDING,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size") or 8192),
                ModelPropertyKey.MAX_CHUNKS: 1,
            },
            features=features,
        )
