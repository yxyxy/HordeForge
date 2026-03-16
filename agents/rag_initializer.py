from __future__ import annotations

import logging
from pathlib import Path

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context

# Импорты для векторной базы данных и эмбеддингов
try:
    import qdrant_client
    from qdrant_client.http import models
except ImportError:
    qdrant_client = None
    models = None

from rag.keyword_index import KeywordIndex
from rag.symbol_extractor import SymbolExtractor
from rag.vector_store import QdrantStore

logger = logging.getLogger(__name__)


def extract_and_index_repository(repo_path: str, collection_name: str = "repo_chunks"):
    """
    Extract symbols from repository and index them in Qdrant with keyword index.

    Args:
        repo_path: Path to the repository to index
        collection_name: Name of the collection to store embeddings in

    Returns:
        Dictionary with indexing results
    """
    try:
        # Initialize vector store and keyword index
        vector_store = QdrantStore()
        keyword_index = KeywordIndex()

        # Create collection if it doesn't exist
        vector_store.create_collection(collection_name)

        # Initialize symbol extractor
        extractor = SymbolExtractor()

        # Walk through all Python files in the repository
        repo_dir = Path(repo_path)
        indexed_count = 0
        total_symbols = 0

        for py_file in repo_dir.rglob("*.py"):
            try:
                # Extract symbols from the Python file
                symbols = extractor.extract_symbols(py_file)

                for symbol in symbols:
                    # Create content for indexing based on symbol type
                    if symbol.type == "class":
                        content = f"class {symbol.name}: {symbol.docstring or ''}"
                    elif symbol.type == "function":
                        params_str = ", ".join(symbol.parameters)
                        content = f"def {symbol.name}({params_str}): {symbol.docstring or ''}"
                    elif symbol.type == "method":
                        params_str = ", ".join(symbol.parameters)
                        content = f"def {symbol.name}({params_str}): {symbol.docstring or ''}"
                    else:
                        content = f"{symbol.name}: {symbol.docstring or ''}"

                    # Add to vector store
                    embedding = vector_store.embed_text([content])[0]

                    # Create a point for Qdrant
                    point = {
                        "id": f"{py_file.as_posix()}#{symbol.name}",
                        "vector": embedding,
                        "payload": {
                            "file_path": py_file.as_posix(),
                            "symbol_name": symbol.name,
                            "symbol_type": symbol.type,
                            "content": content,
                            "line_number": symbol.line_number,
                            "docstring": symbol.docstring,
                            "parameters": symbol.parameters,
                            "class_name": symbol.class_name,
                            "is_async": symbol.is_async,
                        },
                    }

                    # Upsert the point to Qdrant
                    vector_store.upsert(collection_name, [point])

                    # Add to keyword index
                    keyword_index.add_document(
                        doc_id=f"{py_file.as_posix()}#{symbol.name}",
                        content=content,
                        metadata={
                            "file_path": py_file.as_posix(),
                            "symbol_name": symbol.name,
                            "symbol_type": symbol.type,
                            "line_number": symbol.line_number,
                        },
                    )

                    total_symbols += 1

                indexed_count += 1
            except Exception as e:
                logger.warning(f"Error processing file {py_file}: {e}")
                continue

        return {
            "status": "ready",
            "indexed_files": indexed_count,
            "total_symbols": total_symbols,
            "collection_name": collection_name,
            "vector_store_ready": True,
            "keyword_index_ready": True,
        }
    except Exception as e:
        logger.error(f"Error during repository indexing: {e}")
        return {"status": "failed", "error": str(e)}


class RagInitializer(BaseAgent):
    name = "rag_initializer"
    description = "Builds a deterministic lightweight RAG index from repository code."

    def run(self, context: dict) -> dict:
        # Get repository path from context
        repo_path = context.get("repo_path", context.get("repo_url", "./"))

        # Handle git repository URLs by cloning or using local path
        if repo_path.startswith("http"):
            # This would normally involve cloning the repo
            # For now, we'll assume the repo is already available locally
            # or the path has been processed by a previous agent
            repo_path = context.get("local_repo_path", "./")
        else:
            repo_path = repo_path if Path(repo_path).exists() else "./"

        repository_metadata = (
            get_artifact_from_context(
                context,
                "repository_metadata",
                preferred_steps=["repo_connector"],
            )
            or {}
        )

        # Perform repository indexing
        index_result = extract_and_index_repository(repo_path)

        # Determine status based on RAG functionality
        rag_working = index_result["status"] == "ready"
        status = "SUCCESS" if rag_working else "PARTIAL_SUCCESS"
        confidence = 0.95 if rag_working else 0.65

        rag_index = {
            "index_id": f"repo_index_{hash(repo_path)}",
            "indexed_files_count": index_result.get("indexed_files", 0),
            "total_symbols_count": index_result.get("total_symbols", 0),
            "source_repo": repository_metadata.get("full_name", repo_path),
            "deterministic": True,
            "vector_store_status": index_result.get("vector_store_ready", False),
            "keyword_index_status": index_result.get("keyword_index_ready", False),
            "collection_name": index_result.get("collection_name", "repo_chunks"),
            "rag_working": rag_working,
        }

        return build_agent_result(
            status=status,
            artifact_type="rag_index",
            artifact_content=rag_index,
            reason="Repository code index built with symbol extraction and hybrid search capability."
            if rag_working
            else "RAG index initialization failed.",
            confidence=confidence,
            logs=[
                f"Indexed {index_result.get('indexed_files', 0)} files from {repo_path}.",
                f"Extracted {index_result.get('total_symbols', 0)} symbols.",
                f"Vector store status: {'Ready' if index_result.get('vector_store_ready') else 'Failed'}",
                f"Keyword index status: {'Ready' if index_result.get('keyword_index_ready') else 'Failed'}",
            ],
            next_actions=["memory_agent"],
        )
