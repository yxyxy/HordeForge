"""RAG primitives for documentation indexing and context retrieval."""

from rag.embeddings import (
    EmbeddingsProvider,
    HashEmbeddingsProvider,
    MockEmbeddingsProvider,
    create_embeddings_provider,
)
from rag.indexer import DocumentationIndexer
from rag.retriever import ContextRetriever
from rag.ingestion import IngestionPipeline, batch

__all__ = [
    "DocumentationIndexer",
    "ContextRetriever",
    "EmbeddingsProvider",
    "MockEmbeddingsProvider",
    "HashEmbeddingsProvider",
    "create_embeddings_provider",
    "IngestionPipeline",
    "batch",
]
