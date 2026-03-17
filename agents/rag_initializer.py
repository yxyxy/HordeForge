from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context

try:
    from qdrant_client.models import Distance, VectorParams
except ImportError:
    Distance = None
    VectorParams = None

from rag.keyword_index import KeywordIndex
from rag.symbol_extractor import SymbolExtractor
from rag.vector_store import QDRANT_HOST, QDRANT_PORT, QdrantStore

# Optional: async ingestion pipeline for high-performance scenarios
try:
    from rag.ingestion import IngestionPipeline

    ASYNC_INGESTION_AVAILABLE = True
except ImportError:
    ASYNC_INGESTION_AVAILABLE = False

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json"}


def ensure_repo_local(repo_path: str) -> Path:
    """
    Ensures repository is available locally.
    Clones repo if URL is provided.
    """
    path = Path(repo_path)

    if repo_path.startswith("http"):
        local_path = Path("./workspace/repo")

        if not local_path.exists():
            logger.info(f"Cloning repository {repo_path} -> {local_path}")
            subprocess.run(
                ["git", "clone", repo_path, str(local_path)],
                check=True,
            )

        return local_path

    if path.exists():
        return path

    logger.warning(f"Repo path not found: {repo_path}, fallback to ./")
    return Path("./")


def extract_and_index_repository_async(
    repo_path: Path,
    collection_name: str = "repo_chunks",
    batch_size: int = 1024,
    num_workers: int = 8,
):
    """
    High-performance async ingestion using IngestionPipeline.

    Architecture:
    [Reader] → [Batcher] → [Embedder (batched)] → [Async Queue]
                                                        ↓
                                                [Async Upsert Workers]
                                                        ↓
                                                    Qdrant

    Args:
        repo_path: Path to repository
        collection_name: Qdrant collection name
        batch_size: Batch size for embedding and upsert
        num_workers: Number of async upsert workers

    Returns:
        dict: Indexing result with statistics
    """

    vector_store = None
    keyword_index = None
    qdrant_available = False

    try:
        # Create QdrantStore instance for general operations
        vector_store = QdrantStore()
        # Test connection
        vector_store.client.get_collections()
        qdrant_available = True
        logger.info("Qdrant connection established for async ingestion")
    except Exception as e:
        logger.warning(f"Qdrant unavailable: {e}. Falling back to keyword index only.")
        qdrant_available = False

    try:
        keyword_index = KeywordIndex()
        extractor = SymbolExtractor()

        # Create collection if needed
        if qdrant_available:
            # Use the updated QdrantStore.create_collection method with HNSW config
            if not vector_store.collection_exists(collection_name):
                vector_store.create_collection(
                    collection_name=collection_name,
                    vector_size=384,
                    distance=Distance.COSINE,
                    indexing_threshold=1000,
                    hnsw_config={"m": 0},  # Disable index during ingestion for better performance
                )

        indexed_files = 0
        total_symbols = 0

        # Collect all texts first for batched processing
        texts_to_embed = []
        symbol_metadata = []  # Store metadata to pair with embeddings

        files = [
            f for f in repo_path.rglob("*") if f.is_file() and f.suffix in SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.warning("No files found for indexing")

        for file_path in files:
            try:
                if file_path.suffix != ".py":
                    continue

                symbols = extractor.extract_symbols(file_path)

                for symbol in symbols:
                    if symbol.type == "class":
                        content = f"class {symbol.name}: {symbol.docstring or ''}"
                    elif symbol.type in {"function", "method"}:
                        params = ", ".join(symbol.parameters or [])
                        content = f"def {symbol.name}({params}): {symbol.docstring or ''}"
                    else:
                        content = f"{symbol.name}: {symbol.docstring or ''}"

                    texts_to_embed.append(content)
                    symbol_metadata.append(
                        {
                            "file_path": file_path.as_posix(),
                            "symbol_name": symbol.name,
                            "symbol_type": symbol.type,
                            "line_number": symbol.line_number,
                            "docstring": symbol.docstring,
                            "parameters": symbol.parameters,
                            "class_name": symbol.class_name,
                            "is_async": symbol.is_async,
                        }
                    )

                    # Keyword index always works
                    if keyword_index is not None:
                        keyword_index.add_document(
                            doc_id=f"{file_path.as_posix()}#{symbol.name}",
                            content=content,
                            metadata={
                                "file_path": file_path.as_posix(),
                                "symbol_name": symbol.name,
                                "symbol_type": symbol.type,
                                "line_number": symbol.line_number,
                            },
                        )

                    total_symbols += 1

                indexed_files += 1

            except Exception as e:
                logger.warning(f"Error processing file {file_path}: {e}")
                continue

        # Run async ingestion pipeline if Qdrant is available
        if qdrant_available and texts_to_embed:
            try:
                logger.info(
                    f"Starting async ingestion: {len(texts_to_embed)} texts, "
                    f"batch_size={batch_size}, workers={num_workers}"
                )

                # Create async client for the async pipeline
                from qdrant_client import AsyncQdrantClient

                async_client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

                # Use async pipeline
                pipeline = IngestionPipeline(
                    client=async_client,
                    batch_size=batch_size,
                    num_workers=num_workers,
                    queue_size=20,
                )

                # Run async pipeline
                result = pipeline.run_sync(texts_to_embed, collection_name)

                logger.info(
                    f"Async ingestion complete: {result['total_indexed']} points "
                    f"in {result['duration_seconds']}s "
                    f"({result['rate_per_second']}/sec)"
                )

            except Exception as e:
                logger.warning(f"Async ingestion failed, falling back to buffered: {e}")
                # Fallback to buffered approach
                for i, content in enumerate(texts_to_embed):
                    try:
                        embedding = vector_store.embed_text([content])[0]
                        point = {
                            "id": str(uuid4()),
                            "vector": embedding,
                            "payload": symbol_metadata[i],
                        }
                        vector_store.add_point(collection_name, point)
                    except Exception as emb_err:
                        logger.warning(
                            f"Failed to embed {symbol_metadata[i].get('symbol_name')}: {emb_err}"
                        )

                vector_store.close(collection_name)

        status = "ready" if total_symbols > 0 else "failed"

        return {
            "status": status,
            "indexed_files": indexed_files,
            "total_symbols": total_symbols,
            "collection_name": collection_name,
            "vector_store_ready": qdrant_available,
            "keyword_index_ready": keyword_index is not None,
            "async_mode": qdrant_available and ASYNC_INGESTION_AVAILABLE,
        }

    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "vector_store_ready": qdrant_available if vector_store is not None else False,
            "keyword_index_ready": keyword_index is not None,
        }


def create_collection_if_not_exists(vector_store: QdrantStore, collection_name: str):
    """
    Creates Qdrant collection using new API with optimized indexing.
    """
    try:
        if vector_store.collection_exists(collection_name):
            return

        logger.info(f"Creating Qdrant collection: {collection_name}")

        vector_store.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=384,  # bge-small
                distance=Distance.COSINE,
            ),
        )

        # Tune optimizer for faster indexing
        try:
            vector_store.client.update_collection(
                collection_name=collection_name,
                optimizer_config={
                    "indexing_threshold": 1000,  # Start indexing after 1k points (default 20k)
                },
            )
        except Exception as e:
            logger.warning(f"Could not tune optimizer: {e}")

    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise


def extract_and_index_repository(
    repo_path: Path,
    collection_name: str = "repo_chunks",
):
    # Use the async ingestion pipeline instead of the synchronous one
    return extract_and_index_repository_async(
        repo_path=repo_path,
        collection_name=collection_name,
    )


class RagInitializer(BaseAgent):
    name = "rag_initializer"
    description = "Builds RAG index from repository using Qdrant + keyword index."

    def run(self, context: dict) -> dict:
        # Get repository metadata from context (output of repo_connector)
        repository_metadata = (
            get_artifact_from_context(
                context,
                "repository_data",
                preferred_steps=["repo_connector"],
            )
            or {}
        )

        # Use local_path from metadata if available, otherwise fallback to input
        local_path = repository_metadata.get("local_path")
        if local_path:
            repo_path = Path(local_path)
        else:
            # Fallback to input params or default
            repo_path_input = context.get("repo_path") or context.get("repo_url", "./")
            repo_path = ensure_repo_local(repo_path_input)

        index_result = extract_and_index_repository(repo_path)

        rag_working = index_result.get("status") == "ready"
        vector_ready = index_result.get("vector_store_ready", False)
        keyword_ready = index_result.get("keyword_index_ready", False)

        # Determine reason based on what's available
        if rag_working and vector_ready:
            reason = "RAG index built successfully"
        elif rag_working and keyword_ready and not vector_ready:
            reason = "RAG index built with keyword index only (Qdrant unavailable)"
        else:
            reason = "RAG index build failed"

        rag_index = {
            "index_id": f"repo_index_{hash(str(repo_path))}",
            "indexed_files_count": index_result.get("indexed_files", 0),
            "total_symbols_count": index_result.get("total_symbols", 0),
            "source_repo": repository_metadata.get("full_name", str(repo_path)),
            "vector_store_status": vector_ready,
            "keyword_index_status": keyword_ready,
            "collection_name": index_result.get("collection_name"),
            "rag_working": rag_working,
        }

        return build_agent_result(
            status="SUCCESS" if rag_working else "PARTIAL_SUCCESS",
            artifact_type="rag_index",
            artifact_content=rag_index,
            reason=reason,
            confidence=0.95 if rag_working else 0.6,
            logs=[
                f"Repo path: {repo_path}",
                f"Indexed files: {index_result.get('indexed_files', 0)}",
                f"Extracted symbols: {index_result.get('total_symbols', 0)}",
                f"Vector store: {'ready' if vector_ready else 'unavailable'}",
                f"Keyword index: {'ready' if keyword_ready else 'unavailable'}",
            ],
            next_actions=["memory_agent"],
        )
