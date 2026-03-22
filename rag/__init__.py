"""RAG primitives for documentation indexing and context retrieval."""

from rag.embeddings import (
    EmbeddingsProvider,
    HashEmbeddingsProvider,
    MockEmbeddingsProvider,
    create_embeddings_provider,
)
from rag.indexer import DocumentationIndexer
from rag.ingestion import IngestionPipeline, batch
from rag.keyword_index import KeywordIndex
from rag.memory_collections import (
    MemoryEntry,
    MemoryType,
    create_memory_entry,
)
from rag.retriever import ContextRetriever

__all__ = [
    "DocumentationIndexer",
    "ContextRetriever",
    "EmbeddingsProvider",
    "MockEmbeddingsProvider",
    "HashEmbeddingsProvider",
    "create_embeddings_provider",
    "IngestionPipeline",
    "batch",
    "KeywordIndex",
    "MemoryEntry",
    "MemoryType",
    "create_memory_entry",
]
