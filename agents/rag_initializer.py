"""
RAG Initializer Agent — builds vector + keyword index from repository.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context

try:
    from qdrant_client import models
except ImportError:
    models = None

from rag.keyword_index import KeywordIndex
from rag.symbol_extractor import SymbolExtractor
from rag.vector_store import QdrantStore
from rag.config import get_qdrant_host, get_qdrant_port

try:
    from qdrant_client import AsyncQdrantClient

    from rag.ingestion import IngestionPipeline

    ASYNC_INGESTION_AVAILABLE = True
except ImportError:
    ASYNC_INGESTION_AVAILABLE = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".py"}


def ensure_repo_local(repo_path: str) -> Path:
    path = Path(repo_path)
    if repo_path.startswith("http"):
        local_path = Path("./workspace/repo")
        if not local_path.exists():
            logger.info(f"Cloning repository {repo_path} -> {local_path}")
            subprocess.run(
                ["git", "clone", repo_path, str(local_path)],
                check=True,
                capture_output=True,  # 🔥 Тихий клон
            )
        return local_path

    if path.exists():
        return path

    logger.warning(f"Repo path not found: {repo_path}, fallback to ./")
    return Path("./")


def extract_and_index_repository_async(
    repo_path: Path,
    collection_name: str = "repo_chunks",
    batch_size: int = 1024,  # 🔥 Оптимально для баланса скорости/памяти
    num_workers: int = 8,
):
    vector_store = None
    keyword_index = None
    qdrant_available = False

    try:
        vector_store = QdrantStore(check_compatibility=False)
        vector_store.client.get_collections()
        qdrant_available = True
        logger.info("Qdrant connection established for async ingestion")
    except Exception as e:
        logger.warning(f"Qdrant unavailable: {e}. Falling back to keyword index only.")
        qdrant_available = False

    try:
        keyword_index = KeywordIndex()
        extractor = SymbolExtractor()

        if qdrant_available and models:
            if not vector_store.collection_exists(collection_name):
                vector_store.create_collection(
                    collection_name=collection_name,
                    vector_size=384,
                    distance=models.Distance.COSINE,
                    indexing_threshold=1000,
                    hnsw_config={"m": 0},
                )

        indexed_files = 0
        total_symbols = 0
        texts_to_embed = []
        symbol_metadata = []

        files = [
            f for f in repo_path.rglob("*") if f.is_file() and f.suffix in SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.warning("No files found for indexing")

        # 🔥 Прогресс-лог при сборе файлов
        logger.info(f"Scanning {len(files)} Python files for symbols...")

        for idx, file_path in enumerate(files):
            if idx % 10 == 0:
                logger.debug(f"Processing file {idx + 1}/{len(files)}: {file_path}")

            try:
                if file_path.suffix != ".py":
                    continue

                symbols = extractor.extract_symbols(file_path)

                for symbol in symbols:
                    # 🔥 Фильтруем пустые/бесполезные символы
                    if not symbol.name or symbol.name.startswith("_"):
                        continue

                    if symbol.type == "class":
                        content = f"class {symbol.name}: {symbol.docstring or ''}"
                    elif symbol.type in {"function", "method"}:
                        params = ", ".join(symbol.parameters or [])
                        content = f"def {symbol.name}({params}): {symbol.docstring or ''}"
                    else:
                        content = f"{symbol.name}: {symbol.docstring or ''}"

                    # 🔥 Пропускаем слишком короткие тексты (шум)
                    if len(content.strip()) < 20:
                        continue

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
                logger.debug(f"Error processing file {file_path}: {e}")
                continue

        logger.info(f"Extracted {total_symbols:,} symbols from {indexed_files} files")

        if qdrant_available and texts_to_embed and ASYNC_INGESTION_AVAILABLE:
            try:
                logger.info(
                    f"Starting async ingestion: {len(texts_to_embed):,} texts, "
                    f"batch_size={batch_size}, workers={num_workers}"
                )

                async_client = AsyncQdrantClient(
                    host=get_qdrant_host(),
                    port=get_qdrant_port(),
                    prefer_grpc=True,
                    timeout=15,
                    check_compatibility=False,
                )

                logging.getLogger("qdrant_client.async_qdrant_remote").setLevel(logging.ERROR)

                pipeline = IngestionPipeline(
                    client=async_client,
                    batch_size=batch_size,
                    num_workers=num_workers,
                    queue_size=50,
                    check_compatibility=False,
                )

                ingest_start = time.time()
                result = pipeline.run_sync(
                    texts_to_embed,
                    collection_name,
                    metadata_list=symbol_metadata,
                )
                ingest_time = time.time() - ingest_start

                logger.info(f"Ingestion pipeline completed in {ingest_time:.1f}s: {result}")

                logger.info(
                    f"Async ingestion complete: {result['total_indexed']:,} points "
                    f"in {result['duration_seconds']}s "
                    f"({result['rate_per_second']:.0f}/sec)"
                )

                if result.get("verification_status") != "success":
                    logger.warning(
                        f"Verification warning: {result.get('verification_status')}, "
                        f"expected={result.get('expected_points')}, "
                        f"actual={result.get('actual_points')}"
                    )

            except Exception as e:
                logger.warning(f"Async ingestion failed, falling back to buffered: {e}")
                logger.exception("Async ingestion traceback:")

                # Fallback: синхронный апсерт по одному
                for i, content in enumerate(texts_to_embed):
                    try:
                        embedding = vector_store.embed_text([content])[0]
                        meta = symbol_metadata[i] if i < len(symbol_metadata) else {}
                        point = {
                            "id": str(uuid4()),
                            "vector": embedding,
                            "payload": {**meta, "text": content},
                        }
                        vector_store.add_point(collection_name, point)
                        if i % 100 == 0:
                            logger.info(f"Fallback: embedded {i + 1}/{len(texts_to_embed)}")
                    except Exception as emb_err:
                        symbol_name = (
                            symbol_metadata[i].get("symbol_name")
                            if i < len(symbol_metadata)
                            else "unknown"
                        )
                        logger.debug(f"Failed to embed {symbol_name}: {emb_err}")

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
        logger.exception("Indexing traceback:")
        return {
            "status": "failed",
            "error": str(e),
            "vector_store_ready": qdrant_available if vector_store is not None else False,
            "keyword_index_ready": keyword_index is not None,
        }


def extract_and_index_repository(
    repo_path: Path,
    collection_name: str = "repo_chunks",
):
    return extract_and_index_repository_async(
        repo_path=repo_path,
        collection_name=collection_name,
    )


class RagInitializer(BaseAgent):
    name = "rag_initializer"
    description = "Builds RAG index from repository using Qdrant + keyword index."

    def run(self, context: dict) -> dict:
        repository_metadata = (
            get_artifact_from_context(
                context,
                "repository_data",
                preferred_steps=["repo_connector"],
            )
            or {}
        )

        local_path = repository_metadata.get("local_path")
        if local_path:
            repo_path = Path(local_path)
        else:
            repo_path_input = context.get("repo_path") or context.get("repo_url", "./")
            repo_path = ensure_repo_local(repo_path_input)

        index_result = extract_and_index_repository(repo_path)

        rag_working = index_result.get("status") == "ready"
        vector_ready = index_result.get("vector_store_ready", False)
        keyword_ready = index_result.get("keyword_index_ready", False)

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
