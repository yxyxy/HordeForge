"""
RAG configuration - centralized embedding model and vector store configuration.
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


def get_vector_store_mode() -> str:
    """
    Get the vector store mode to use for RAG operations.
    Can be 'local', 'host', or 'auto'.

    Can be configured via HORDEFORGE_VECTOR_STORE_MODE environment variable.
    Default is 'auto' which tries host mode first and falls back to local if host is unavailable.

    Returns:
        str: Vector store mode ('local', 'host', or 'auto')
    """
    mode = os.getenv("HORDEFORGE_VECTOR_STORE_MODE", "auto").lower()
    if mode not in ["local", "host", "auto"]:
        mode = "auto"  # fallback to auto if invalid value provided
    return mode


def get_qdrant_host() -> str:
    """
    Get the Qdrant host to use for RAG operations.
    Used when vector store mode is 'host' or 'auto'.

    Can be configured via QDRANT_HOST environment variable.
    Default is 'qdrant' for Docker or 'localhost' for local development.

    Returns:
        str: Qdrant host
    """
    return os.getenv("QDRANT_HOST", "qdrant")


def get_qdrant_port() -> int:
    """
    Get the Qdrant port to use for RAG operations.
    Used when vector store mode is 'host' or 'auto'.

    Can be configured via QDRANT_PORT environment variable.
    Default is 6333 which is the standard Qdrant port.

    Returns:
        int: Qdrant port
    """
    return int(os.getenv("QDRANT_PORT", "6333"))
