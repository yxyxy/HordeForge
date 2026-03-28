from __future__ import annotations

import pytest

from rag.embeddings import (
    HashEmbeddingsProvider,
    MockEmbeddingsProvider,
    cosine_similarity,
    create_embeddings_provider,
)


def test_hash_provider_returns_stable_dimension_for_single_and_batch_embeddings():
    provider = HashEmbeddingsProvider(dimension=24)

    vector = provider.embed_text("deterministic retries")
    batch = provider.embed_texts(["deterministic retries", "security tokens"])

    assert len(vector) == 24
    assert len(batch) == 2
    assert all(len(item) == 24 for item in batch)


def test_mock_provider_uses_custom_vector_mapping():
    provider = MockEmbeddingsProvider(
        dimension=4,
        vectors={"hello": [1.0, 2.0, 0.0, 0.0]},
    )

    hello = provider.embed_text("hello")
    other = provider.embed_text("world")

    assert len(hello) == 4
    assert len(other) == 4
    assert hello != other
    assert hello[0] > 0


def test_create_embeddings_provider_supports_hash_and_mock_backends():
    assert create_embeddings_provider("hash").name == "hash"
    assert create_embeddings_provider("mock").name == "mock"
    with pytest.raises(ValueError, match="Unsupported embeddings provider"):
        create_embeddings_provider("unknown-provider")


def test_cosine_similarity_prefers_related_vectors():
    provider = HashEmbeddingsProvider(dimension=32)
    query = provider.embed_text("retry pipeline failures")
    related = provider.embed_text("pipeline retry strategy for failures")
    unrelated = provider.embed_text("database migration planning")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)
