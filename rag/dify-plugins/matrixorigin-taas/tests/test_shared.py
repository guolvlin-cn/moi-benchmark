import base64

import pytest
from dify_plugin.entities.model.text_embedding import MultiModalContent, MultiModalContentType

from models.llm.llm import MatrixOriginTaaSLargeLanguageModel
from models.rerank.rerank import MatrixOriginTaaSRerankModel
from models.shared import image_data_url, multimodal_content
from models.text_embedding.text_embedding import MatrixOriginTaaSTextEmbeddingModel


def test_png_base64_is_wrapped_as_data_url() -> None:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\npayload").decode()
    assert image_data_url(png) == f"data:image/png;base64,{png}"


def test_existing_url_is_preserved() -> None:
    assert image_data_url("https://example.com/image.png") == "https://example.com/image.png"


def test_unknown_binary_is_rejected() -> None:
    with pytest.raises(Exception, match="Unsupported image format"):
        image_data_url(base64.b64encode(b"not an image").decode())


def test_text_is_translated_to_taas_content_parts() -> None:
    document = MultiModalContent(
        content_type=MultiModalContentType.TEXT,
        content="hello",
    )
    assert multimodal_content(document) == {
        "content": [{"type": "text", "text": "hello"}]
    }


def test_image_is_translated_to_taas_content_parts() -> None:
    image_url = "https://example.com/image.png"
    document = MultiModalContent(
        content_type=MultiModalContentType.IMAGE,
        content=image_url,
    )
    assert multimodal_content(document) == {
        "content": [{"type": "image_url", "image_url": {"url": image_url}}]
    }


def test_model_classes_are_concrete() -> None:
    MatrixOriginTaaSLargeLanguageModel([])
    MatrixOriginTaaSTextEmbeddingModel([])
    MatrixOriginTaaSRerankModel([])
