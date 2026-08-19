"""BGE-M3 model loading and dense-embedding primitives.

The HTTP layer lives in :mod:`app`. Keeping model loading here makes the
request contract easy to test without downloading model weights.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union


LOGGER = logging.getLogger(__name__)

BGE_M3_DIMENSION = 1024
BGE_M3_MAX_LENGTH = 8192
DEFAULT_MAX_BATCH = 64
DEFAULT_MAX_BATCH_BYTES = 256 * 1024


class EmbeddingInputError(ValueError):
    """A client supplied an invalid embedding request."""


class ModelUnavailableError(RuntimeError):
    """The local embedding model could not be loaded or used."""


class EmbeddingOutputError(RuntimeError):
    """The model returned a vector payload that cannot be stored safely."""


def _optional_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    value = _optional_env(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _env_bool(name: str, default: bool) -> bool:
    value = _optional_env(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be one of true/false")


def resolve_device(requested: str) -> str:
    """Resolve ``auto`` without importing torch until the service needs it."""

    normalized = requested.strip().lower()
    if normalized and normalized != "auto":
        return requested.strip()

    try:
        import torch  # type: ignore
    except Exception:
        return "cpu"

    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        LOGGER.debug("CUDA availability check failed", exc_info=True)

    try:
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        LOGGER.debug("MPS availability check failed", exc_info=True)

    return "cpu"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the local service.

    ``model`` is the Hugging Face identifier or a local snapshot path used to
    load weights. ``model_id`` is the stable OpenAI-compatible identifier
    returned to clients; keeping these separate allows a local snapshot to be
    used while the RAG config continues to request ``BAAI/bge-m3``.
    """

    model: str = "BAAI/bge-m3"
    model_id: str = "BAAI/bge-m3"
    model_dir: Optional[str] = None
    cache_dir: Optional[str] = None
    device: str = "cpu"
    use_fp16: bool = False
    batch_size: int = 8
    max_length: int = BGE_M3_MAX_LENGTH
    max_batch: int = DEFAULT_MAX_BATCH
    max_batch_bytes: int = DEFAULT_MAX_BATCH_BYTES
    dimension: int = BGE_M3_DIMENSION
    api_key: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 8081
    lazy_load: bool = True
    local_files_only: bool = False

    @property
    def model_source(self) -> str:
        return self.model_dir or self.model

    @classmethod
    def from_env(cls) -> "Settings":
        model = _optional_env("BGE_MODEL") or "BAAI/bge-m3"
        model_dir = _optional_env("BGE_MODEL_DIR")
        model_id = _optional_env("BGE_MODEL_ID")
        if model_id is None:
            # A path is an implementation detail; expose the canonical model
            # id by default so the RAG client can keep using BAAI/bge-m3.
            model_id = "BAAI/bge-m3" if model_dir else model

        device = resolve_device(_optional_env("BGE_DEVICE") or "auto")
        explicit_fp16 = _optional_env("BGE_USE_FP16")
        use_fp16 = (
            _env_bool("BGE_USE_FP16", False)
            if explicit_fp16 is not None
            else device.lower().startswith("cuda")
        )
        max_length = _env_int("BGE_MAX_LENGTH", BGE_M3_MAX_LENGTH)
        if max_length > BGE_M3_MAX_LENGTH:
            raise ValueError(f"BGE_MAX_LENGTH must be <= {BGE_M3_MAX_LENGTH}")

        return cls(
            model=model,
            model_id=model_id,
            model_dir=model_dir,
            cache_dir=_optional_env("BGE_CACHE_DIR"),
            device=device,
            use_fp16=use_fp16,
            batch_size=_env_int("BGE_BATCH_SIZE", 8),
            max_length=max_length,
            max_batch=_env_int("BGE_MAX_BATCH", DEFAULT_MAX_BATCH),
            max_batch_bytes=_env_int("BGE_MAX_BATCH_BYTES", DEFAULT_MAX_BATCH_BYTES),
            dimension=_env_int("BGE_DIMENSION", BGE_M3_DIMENSION),
            api_key=_optional_env("BGE_API_KEY"),
            host=_optional_env("BGE_HOST") or "127.0.0.1",
            port=_env_int("BGE_PORT", 8081),
            lazy_load=_env_bool("BGE_LAZY_LOAD", True),
            local_files_only=_env_bool("BGE_LOCAL_FILES_ONLY", False),
        )

    def public_dict(self) -> Dict[str, Any]:
        """Return health metadata without exposing secrets."""

        return {
            "model": self.model_id,
            "model_source": self.model_source,
            "device": self.device,
            "use_fp16": self.use_fp16,
            "batch_size": self.batch_size,
            "max_length": self.max_length,
            "dimension": self.dimension,
            "lazy_load": self.lazy_load,
            "local_files_only": self.local_files_only,
        }


def normalize_inputs(
    value: Union[str, Sequence[str]], *, max_batch: int, max_batch_bytes: int
) -> List[str]:
    """Validate and normalize the OpenAI ``input`` field."""

    if isinstance(value, str):
        texts = [value]
    elif isinstance(value, (list, tuple)):
        texts = list(value)
    else:
        raise EmbeddingInputError("input must be a string or an array of strings")

    if not texts:
        raise EmbeddingInputError("input must contain at least one string")
    if len(texts) > max_batch:
        raise EmbeddingInputError(f"input contains {len(texts)} items; maximum is {max_batch}")

    total_bytes = 0
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise EmbeddingInputError(f"input[{index}] must be a string")
        if not text.strip():
            raise EmbeddingInputError(f"input[{index}] must not be empty")
        total_bytes += len(text.encode("utf-8"))
    if total_bytes > max_batch_bytes:
        raise EmbeddingInputError(
            f"input payload is {total_bytes} UTF-8 bytes; maximum is {max_batch_bytes}"
        )
    return texts


def estimate_prompt_tokens(texts: Sequence[str]) -> int:
    """Return a cheap usage estimate when tokenizer accounting is unavailable."""

    # Usage is informational for the local RAG client. Four UTF-8 bytes is a
    # deliberately conservative multilingual approximation and avoids running
    # the tokenizer a second time for every request.
    return sum(max(1, (len(text.encode("utf-8")) + 3) // 4) for text in texts)


def _is_real(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def vectors_to_rows(value: Any, *, expected_count: int, expected_dimension: int) -> List[List[float]]:
    """Convert numpy/torch/list output into JSON- and MatrixOne-safe rows."""

    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise EmbeddingOutputError("embedding model returned a non-array dense vector payload")

    # A one-item encode can return a flat vector depending on the backend.
    if value and _is_real(value[0]):
        value = [value]
    if len(value) != expected_count:
        raise EmbeddingOutputError(
            f"embedding model returned {len(value)} vectors for {expected_count} inputs"
        )

    rows: List[List[float]] = []
    for row_index, row in enumerate(value):
        if hasattr(row, "detach"):
            row = row.detach().cpu()
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (list, tuple)):
            raise EmbeddingOutputError(f"embedding row {row_index} is not an array")
        if len(row) != expected_dimension:
            raise EmbeddingOutputError(
                f"embedding row {row_index} has dimension {len(row)}; expected {expected_dimension}"
            )
        converted: List[float] = []
        for value_index, number in enumerate(row):
            if not _is_real(number):
                raise EmbeddingOutputError(
                    f"embedding row {row_index} value {value_index} is not numeric"
                )
            converted_number = float(number)
            if not math.isfinite(converted_number):
                raise EmbeddingOutputError(
                    f"embedding row {row_index} value {value_index} is not finite"
                )
            converted.append(converted_number)
        rows.append(converted)
    return rows


class EmbeddingEngine:
    """Thread-safe lazy wrapper around the official FlagEmbedding model."""

    def __init__(
        self,
        settings: Settings,
        model_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.settings = settings
        self._model_factory = model_factory or self._load_flag_embedding_model
        self._model: Any = None
        self._load_error: Optional[str] = None
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def status(self) -> Dict[str, Any]:
        if self._load_error:
            status = "error"
        elif self.loaded:
            status = "ok"
        else:
            status = "not_loaded"
        return {"status": status, "ready": self.loaded, **self.settings.public_dict()}

    def _load_flag_embedding_model(self) -> Any:
        cache_dir: Optional[str] = None
        if self.settings.cache_dir:
            cache_dir = str(Path(self.settings.cache_dir).expanduser())
            os.environ.setdefault("HF_HOME", cache_dir)
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(cache_dir) / "hub"))
            os.environ.setdefault("TRANSFORMERS_CACHE", str(Path(cache_dir) / "transformers"))
        if self.settings.local_files_only:
            os.environ["HF_HUB_OFFLINE"] = "1"

        try:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore
        except Exception as exc:
            raise ModelUnavailableError(
                "FlagEmbedding is not installed; run `uv sync` in "
                "prototypes/local-bge-m3-embedding"
            ) from exc

        try:
            # BGEM3FlagModel is the official repository's public BGE-M3 API.
            # It accepts a torch device string and performs dense/sparse/ColBERT
            # inference; this service deliberately requests dense vectors only.
            return BGEM3FlagModel(
                self.settings.model_source,
                use_fp16=self.settings.use_fp16,
                devices=self.settings.device,
                cache_dir=cache_dir,
            )
        except Exception as exc:
            raise ModelUnavailableError(
                f"failed to load BGE-M3 model from {self.settings.model_source!r} "
                f"on device {self.settings.device!r}: {exc}"
            ) from exc

    def _ensure_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            if self._load_error:
                raise ModelUnavailableError(self._load_error)
            try:
                self._model = self._model_factory()
            except Exception as exc:
                self._load_error = str(exc)
                LOGGER.exception("BGE-M3 model load failed")
                if isinstance(exc, ModelUnavailableError):
                    raise
                raise ModelUnavailableError(self._load_error) from exc
            return self._model

    def load(self) -> None:
        """Eagerly load the model, useful for a readiness check."""

        self._ensure_model()

    def embed(self, value: Union[str, Sequence[str]]) -> List[List[float]]:
        texts = normalize_inputs(
            value,
            max_batch=self.settings.max_batch,
            max_batch_bytes=self.settings.max_batch_bytes,
        )
        model = self._ensure_model()
        try:
            with self._lock:
                output = model.encode(
                    texts,
                    batch_size=self.settings.batch_size,
                    max_length=self.settings.max_length,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )
        except Exception as exc:
            LOGGER.exception("BGE-M3 encoding failed")
            raise ModelUnavailableError(f"BGE-M3 encoding failed: {exc}") from exc

        if isinstance(output, dict):
            dense = output.get("dense_vecs")
        else:
            dense = output
        if dense is None:
            raise EmbeddingOutputError("embedding model response has no dense_vecs field")
        return vectors_to_rows(
            dense,
            expected_count=len(texts),
            expected_dimension=self.settings.dimension,
        )
