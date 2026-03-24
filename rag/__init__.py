"""RAG (Retrieval Augmented Generation) module for HordeForge AI development orchestrator."""

# Core components
# Chunking components
from rag.chunking import ChunkGenerator, CodeElement, CodeStructureAnalyzer, SmartChunker
from rag.config import get_embedding_model, get_qdrant_host, get_qdrant_port
from rag.context_builder import ContextBuilder
from rag.context_compressor import ContextCompressor
from rag.deduplicator import Deduplicator
from rag.hybrid_retriever import HybridRetriever
from rag.indexer import DocumentationIndexer
from rag.ingestion import IngestionPipeline
from rag.keyword_index import KeywordIndex
from rag.memory_retriever import MemoryRetriever
from rag.memory_store import MemoryStore

# Models
from rag.models import Chunk, Symbol
from rag.retriever import ContextRetriever

# Stages for structured indexing
from rag.stages import (
    ChunkingStage,
    EmbeddingStage,
    ParsedFile,
    ParsingStage,
    StorageStage,
    SymbolExtractionStage,
)
from rag.vector_store import QdrantStore

__all__ = [
    # Core components
    "IngestionPipeline",
    "ContextRetriever",
    "HybridRetriever",
    "MemoryRetriever",
    "DocumentationIndexer",
    "get_embedding_model",
    "get_qdrant_host",
    "get_qdrant_port",
    "QdrantStore",
    "KeywordIndex",
    "MemoryStore",
    "ContextBuilder",
    "ContextCompressor",
    "Deduplicator",
    # Stages
    "ParsingStage",
    "SymbolExtractionStage",
    "ChunkingStage",
    "EmbeddingStage",
    "StorageStage",
    "ParsedFile",
    "Symbol",
    "Chunk",
    # Chunking components
    "CodeStructureAnalyzer",
    "SmartChunker",
    "ChunkGenerator",
    "CodeElement",
]
