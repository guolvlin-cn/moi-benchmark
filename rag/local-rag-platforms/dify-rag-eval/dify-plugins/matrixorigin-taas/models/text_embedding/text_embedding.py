from __future__ import annotations

import time
import threading
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


# Dify's indexing runner fans a document out to several embedding threads.
# MaaS supports batched inputs.  Two sustained outbound requests plus a short
# start-rate guard avoid the provider's burst-as-401 behavior while Dify keeps
# parsing and vector writes parallel across four workers.
_EMBEDDING_REQUEST_SLOT = threading.BoundedSemaphore(8)
_EMBEDDING_RATE_LOCK = threading.Lock()
_MAAS_BATCH_SIZE = 32
_RETRYABLE_EMBEDDING_ERRORS = (
    InvokeAuthorizationError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
_EMBEDDING_RETRY_DELAYS = (2.0, 4.0, 8.0, 16.0, 32.0, 64.0)
_EMBEDDING_MIN_INTERVAL_SECONDS = 0.25
_LAST_EMBEDDING_REQUEST_AT = 0.0


def _post_embedding_with_retry(credentials: dict, payload: dict) -> dict:
    """Retry transient MaaS failures while retaining one outbound request slot.

    MaaS occasionally reports burst throttling as HTTP 401/403. A genuinely
    invalid key still fails after this short, bounded retry window and is
    surfaced unchanged to Dify.
    """
    global _LAST_EMBEDDING_REQUEST_AT

    for attempt in range(len(_EMBEDDING_RETRY_DELAYS) + 1):
        minimum_interval = (
            _EMBEDDING_MIN_INTERVAL_SECONDS
            if "modelarts-maas" in str(credentials.get("base_url") or "").casefold()
            else 0.0
        )
        with _EMBEDDING_RATE_LOCK:
            now = time.monotonic()
            throttle_delay = minimum_interval - (now - _LAST_EMBEDDING_REQUEST_AT)
            if throttle_delay > 0:
                time.sleep(throttle_delay)
            _LAST_EMBEDDING_REQUEST_AT = time.monotonic()
        try:
            return post_json(credentials, "/embeddings", payload)
        except _RETRYABLE_EMBEDDING_ERRORS:
            if attempt == len(_EMBEDDING_RETRY_DELAYS):
                raise
            time.sleep(_EMBEDDING_RETRY_DELAYS[attempt])

    raise AssertionError("unreachable")


def _is_qianfan(credentials: dict) -> bool:
    return "qianfan.baidubce.com" in str(credentials.get("base_url") or "").casefold()


def _is_maas(credentials: dict) -> bool:
    return "modelarts-maas" in str(credentials.get("base_url") or "").casefold()


class MatrixOriginTaaSTextEmbeddingModel(TextEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        embeddings: list[list[float]]
        total_tokens: int

        if _is_qianfan(credentials) and texts:
            with _EMBEDDING_REQUEST_SLOT:
                response = _post_embedding_with_retry(
                    credentials,
                    {
                        "model": model,
                        "input": texts,
                        "encoding_format": "float",
                    },
                )
            embeddings, total_tokens = self._parse_batch_embeddings(response, len(texts))
        elif _is_maas(credentials) and texts:
            embeddings = []
            total_tokens = 0
            for offset in range(0, len(texts), _MAAS_BATCH_SIZE):
                batch = texts[offset : offset + _MAAS_BATCH_SIZE]
                with _EMBEDDING_REQUEST_SLOT:
                    response = _post_embedding_with_retry(
                        credentials,
                        {
                            "model": model,
                            "input": batch,
                            "encoding_format": "float",
                        },
                    )
                batch_embeddings, batch_tokens = self._parse_batch_embeddings(response, len(batch))
                embeddings.extend(batch_embeddings)
                total_tokens += batch_tokens
        else:
            embeddings = []
            total_tokens = 0

            # TaaS and MaaS currently use one request per input. Keep this
            # path sequential so their existing throttle/retry behavior and
            # one-input/one-output cardinality remain unchanged.
            for text in texts:
                with _EMBEDDING_REQUEST_SLOT:
                    response = _post_embedding_with_retry(
                        credentials,
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
            with _EMBEDDING_REQUEST_SLOT:
                response = _post_embedding_with_retry(
                    credentials,
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

    @staticmethod
    def _parse_batch_embeddings(
        response: dict, expected_count: int
    ) -> tuple[list[list[float]], int]:
        data = response.get("data")
        actual_count = len(data) if isinstance(data, list) else 0
        if not isinstance(data, list) or actual_count != expected_count:
            raise ValueError(
                "Qianfan embedding response expected "
                f"{expected_count} results, got {actual_count}"
            )

        indexed: list[tuple[int, list[float]]] = []
        for position, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Qianfan embedding response is missing data[{position}].embedding"
                )
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise ValueError(
                    f"Qianfan embedding response is missing data[{position}].embedding"
                )
            response_index = item.get("index", position)
            if not isinstance(response_index, int) or not 0 <= response_index < expected_count:
                raise ValueError(f"Qianfan embedding response has invalid data[{position}].index")
            indexed.append((response_index, [float(value) for value in vector]))

        if len({index for index, _ in indexed}) != expected_count:
            raise ValueError("Qianfan embedding response has duplicate indexes")
        embeddings = [vector for _, vector in sorted(indexed)]

        usage = response.get("usage") or {}
        total_tokens = int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
        return embeddings, total_tokens

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
                ModelPropertyKey.MAX_CHUNKS: 32,
            },
            features=features,
        )
