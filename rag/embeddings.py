from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from hashlib import sha256

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _normalize_vector(vector: list[float], *, dimension: int) -> list[float]:
    normalized_dimension = max(1, int(dimension))
    if len(vector) < normalized_dimension:
        padded = vector + [0.0] * (normalized_dimension - len(vector))
    else:
        padded = vector[:normalized_dimension]
    norm = math.sqrt(sum(item * item for item in padded))
    if norm <= 0:
        return [0.0] * normalized_dimension
    return [item / norm for item in padded]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(item * item for item in left[:size]))
    right_norm = math.sqrt(sum(item * item for item in right[:size]))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


class EmbeddingsProvider(ABC):
    name = "base"

    def __init__(self, *, dimension: int = 64) -> None:
        self.dimension = max(1, int(dimension))

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_text(item) for item in texts]


class MockEmbeddingsProvider(EmbeddingsProvider):
    name = "mock"

    def __init__(
        self,
        *,
        dimension: int = 16,
        vectors: dict[str, list[float]] | None = None,
    ) -> None:
        super().__init__(dimension=dimension)
        self._vectors = dict(vectors or {})

    @staticmethod
    def _fallback_tokens(text: str) -> list[str]:
        return _TOKEN_PATTERN.findall(str(text).lower())

    def embed_text(self, text: str) -> list[float]:
        raw_text = str(text)
        mapped = self._vectors.get(raw_text)
        if isinstance(mapped, list):
            numeric = [float(item) for item in mapped]
            return _normalize_vector(numeric, dimension=self.dimension)

        tokens = self._fallback_tokens(raw_text)
        vector = [0.0] * self.dimension
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        return _normalize_vector(vector, dimension=self.dimension)


class HashEmbeddingsProvider(EmbeddingsProvider):
    name = "hash"

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return _TOKEN_PATTERN.findall(str(text).lower())

    def embed_text(self, text: str) -> list[float]:
        tokens = self._tokens(text)
        vector = [0.0] * self.dimension
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = -1.0 if (digest[4] & 1) else 1.0
            vector[index] += sign
        return _normalize_vector(vector, dimension=self.dimension)


def create_embeddings_provider(
    provider_name: str,
    *,
    dimension: int = 64,
) -> EmbeddingsProvider:
    normalized = str(provider_name).strip().lower()
    if normalized in {"hash", "local_hash", "deterministic_hash"}:
        return HashEmbeddingsProvider(dimension=dimension)
    if normalized in {"mock", "test"}:
        return MockEmbeddingsProvider(dimension=dimension)
    raise ValueError(f"Unsupported embeddings provider: {provider_name}")


def resolve_embeddings_provider(
    *,
    provider: EmbeddingsProvider | None = None,
    provider_name: str | None = None,
    dimension: int = 64,
) -> EmbeddingsProvider | None:
    if provider is not None:
        return provider
    normalized = str(provider_name or "hash").strip().lower()
    if normalized in {"none", "disabled", "off"}:
        return None
    return create_embeddings_provider(normalized, dimension=dimension)
