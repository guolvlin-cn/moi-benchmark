from __future__ import annotations

from typing import Optional

from dify_plugin import RerankModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.entities.model.text_embedding import MultiModalContent
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.rerank_model import MultiModalRerankResult

from models.shared import multimodal_content, post_json


class MatrixOriginTaaSRerankModel(RerankModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        query: str,
        docs: list[str],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> RerankResult:
        if not docs:
            return RerankResult(model=model, docs=[])

        response = post_json(
            credentials,
            "/rerank",
            {
                "model": model,
                "query": query,
                "documents": docs,
                "top_n": top_n or len(docs),
                "return_documents": False,
            },
        )
        return RerankResult(
            model=model,
            docs=self._parse_results(response, docs, score_threshold),
        )

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        query: MultiModalContent,
        docs: list[MultiModalContent],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> MultiModalRerankResult:
        if not docs:
            return MultiModalRerankResult(model=model, docs=[])

        response = post_json(
            credentials,
            "/rerank",
            {
                "model": model,
                "query": multimodal_content(query),
                "documents": [multimodal_content(doc) for doc in docs],
                "top_n": top_n or len(docs),
                "return_documents": False,
            },
        )
        return MultiModalRerankResult(
            model=model,
            docs=self._parse_results(
                response,
                [doc.content for doc in docs],
                score_threshold,
            ),
        )

    @staticmethod
    def _parse_results(
        response: dict,
        docs: list[str],
        score_threshold: Optional[float],
    ) -> list[RerankDocument]:
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise ValueError("TaaS rerank response is missing results")

        results: list[RerankDocument] = []
        for item in raw_results:
            index = int(item["index"])
            score = float(item["relevance_score"])
            if index < 0 or index >= len(docs):
                raise ValueError(f"TaaS returned invalid document index: {index}")
            if score_threshold is None or score >= score_threshold:
                results.append(
                    RerankDocument(
                        index=index,
                        text=docs[index],
                        score=score,
                    )
                )
        return results

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                query="capital of China",
                docs=["Beijing is the capital of China.", "Paris is in France."],
                top_n=1,
            )
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

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        features = []
        if credentials.get("vision_support") == "support":
            features.append(ModelFeature.VISION)
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.RERANK,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size") or 8192)
            },
            features=features,
        )
