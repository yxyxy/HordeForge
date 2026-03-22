"""
RAG configuration - centralized embedding model configuration.
"""

from __future__ import annotations

import os

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def get_embedding_model() -> str:
    """
    Get the embedding model to use for RAG operations.

    Can be configured via HORDEFORGE_EMBEDDING_MODEL environment variable.

    Returns:
        str: Model name for TextEmbedding
    """
    return os.getenv("HORDEFORGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
