from __future__ import annotations

import logging
import os
import re
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from storage.backends import StorageBackend, get_storage_backend

try:
    from rag.vector_store import QdrantStore
except Exception:  # noqa: BLE001
    QdrantStore = None

_QDRANT_STORE_CACHE: Any | None = None
logger = logging.getLogger(__name__)


class MemoryType(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "Creates an initial downstream-ready memory state."

    def __init__(self):
        self.storage: StorageBackend | None = None

    def run(self, context: dict[str, Any]) -> dict:
        # Try both artifact types: repository_data (from repo_connector) and repository_metadata
        repository_metadata = (
            get_artifact_from_context(
                context,
                "repository_data",
                preferred_steps=["repo_connector"],
            )
            or get_artifact_from_context(
                context,
                "repository_metadata",
                preferred_steps=["repo_connector"],
            )
            or {}
        )
        rag_index = (
            get_artifact_from_context(
                context,
                "rag_index",
                preferred_steps=["rag_initializer"],
            )
            or {}
        )

        raw_query = context.get("query")
        query = self._resolve_query(raw_query, context)
        if isinstance(query, str) and query.strip():
            memory_context = self._build_memory_context(query.strip(), rag_index)
            return build_agent_result(
                status="SUCCESS",
                artifact_type="memory_context",
                artifact_content=memory_context,
                reason="Memory context retrieved from indexed documents.",
                confidence=0.84 if memory_context.get("matches") else 0.72,
                logs=[
                    f"Memory retrieval query received: {query.strip()[:120]}",
                    f"Memory retrieval matches: {len(memory_context.get('matches', []))}.",
                ],
                next_actions=["code_generator", "architecture_planner"],
            )

        repository_input = context.get("repository")
        has_repository_input = isinstance(repository_input, dict) and bool(
            str(repository_input.get("full_name") or "").strip()
        )

        has_repo = bool(repository_metadata)
        if not has_repo and has_repository_input:
            full_name = str(repository_input.get("full_name")).strip()
            owner, _, repo_name = full_name.partition("/")
            repository_metadata = {
                "owner": owner or "unknown",
                "repo_name": repo_name or "unknown",
                "full_name": full_name,
            }
            has_repo = True
        has_rag = bool(rag_index)
        status = "SUCCESS" if has_repo and has_rag else "PARTIAL_SUCCESS"
        memory_state = {
            "schema_version": "1.0",
            "repository": {
                "owner": repository_metadata.get("owner", "unknown"),
                "repo_name": repository_metadata.get("repo_name", "unknown"),
                "full_name": repository_metadata.get("full_name", "unknown"),
            },
            "knowledge": {
                "documents_count": rag_index.get("documents_count", 0),
                "index_id": rag_index.get("index_id", "rag_index_missing"),
            },
            "events": [
                {
                    "type": "memory_initialized",
                    "source": "memory_agent",
                }
            ],
            "ready_for_downstream": True,
        }

        return build_agent_result(
            status=status,
            artifact_type="memory_state",
            artifact_content=memory_state,
            reason="Memory state seeded from repository metadata and docs index.",
            confidence=0.86 if status == "SUCCESS" else 0.7,
            logs=[
                "Initial memory state prepared.",
                f"Repository metadata present: {has_repo}.",
                f"RAG index present: {has_rag}.",
            ],
            next_actions=["architecture_evaluator", "test_analyzer"],
        )

    def _resolve_query(self, raw_query: Any, context: dict[str, Any]) -> str:
        if isinstance(raw_query, str):
            query = raw_query.strip()
            if query and "{{" not in query and "}}" not in query:
                return query

        issue = context.get("issue")
        if not isinstance(issue, dict):
            return ""

        parts: list[str] = []
        title = issue.get("title")
        body = issue.get("body")
        comments_context = issue.get("comments_context")
        comments = issue.get("comments")

        if isinstance(title, str) and title.strip():
            parts.append(title.strip())
        if isinstance(body, str) and body.strip():
            parts.append(body.strip())
        if isinstance(comments_context, str) and comments_context.strip():
            parts.append(comments_context.strip())
        if isinstance(comments, list):
            comment_bodies: list[str] = []
            for item in comments:
                if not isinstance(item, dict):
                    continue
                body_value = item.get("body")
                if isinstance(body_value, str) and body_value.strip():
                    comment_bodies.append(body_value.strip())
            if comment_bodies:
                parts.append("\n".join(comment_bodies[:10]))

        return "\n".join(part for part in parts if part)

    def _build_memory_context(self, query: str, rag_index: dict[str, Any]) -> dict[str, Any]:
        semantic_matches = self._semantic_search(query=query, rag_index=rag_index, limit=8)

        documents = rag_index.get("documents")
        if not isinstance(documents, list):
            documents = []

        query_tokens = self._tokenize(query)
        lexical_matches: list[dict[str, Any]] = []

        for item in documents:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            summary = str(item.get("summary", "")).strip()
            content = str(item.get("content", "")).strip()
            searchable = f"{path} {summary} {content}".strip()
            score = self._overlap_score(query_tokens, self._tokenize(searchable))
            if score <= 0:
                continue
            lexical_matches.append(
                {
                    "path": path or "unknown",
                    "summary": summary or content[:200],
                    "score": float(score),
                    "source": "lexical",
                }
            )

        lexical_matches.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)

        merged: dict[str, dict[str, Any]] = {}
        for item in semantic_matches + lexical_matches:
            key = f"{item.get('path')}|{item.get('summary')}"
            existing = merged.get(key)
            if existing is None or float(item.get("score", 0.0)) > float(
                existing.get("score", 0.0)
            ):
                merged[key] = item

        ranked_matches = sorted(
            merged.values(),
            key=lambda item: float(item.get("score", 0.0)),
            reverse=True,
        )
        collection_name = str(rag_index.get("collection_name") or "repo_chunks")

        return {
            "query": query,
            "matches": ranked_matches[:5],
            "documents_count": self._resolve_documents_count(
                rag_index=rag_index,
                collection_name=collection_name,
                fallback_count=len(documents),
            ),
            "collection_name": collection_name,
        }

    def _semantic_search(
        self, *, query: str, rag_index: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        if QdrantStore is None:
            return []

        collection_name = str(rag_index.get("collection_name") or "repo_chunks").strip()
        if not collection_name:
            collection_name = "repo_chunks"

        try:
            store = self._get_semantic_store()
            if store is None:
                return []
            query_vectors = store.embed_text([query])
            if not query_vectors:
                return []
            results = store.search(
                collection_name=collection_name,
                query_vector=query_vectors[0],
                limit=max(1, int(limit)),
            )
        except Exception as error:
            logger.warning(
                "memory_semantic_search_failed collection=%s error=%s",
                collection_name,
                error,
            )
            return []

        matches: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            text = str(payload.get("text", "")).strip()
            path = str(payload.get("file_path", "")).strip() or "unknown"
            symbol_name = str(payload.get("symbol_name", "")).strip()
            summary = text[:220] if text else symbol_name or "semantic_match"
            score = float(result.get("score", 0.0) or 0.0)
            if score <= 0:
                continue
            matches.append(
                {
                    "path": path,
                    "summary": summary,
                    "score": score,
                    "source": "semantic",
                }
            )
        return matches

    def _resolve_documents_count(
        self, *, rag_index: dict[str, Any], collection_name: str, fallback_count: int
    ) -> int:
        raw_count = rag_index.get("documents_count")
        try:
            count = int(raw_count or 0)
        except Exception:
            count = 0
        if count > 0:
            return count

        try:
            store = self._get_semantic_store()
            if store is not None and hasattr(store, "get_collection_points_count"):
                collection_points = store.get_collection_points_count(collection_name)
                if collection_points is not None and int(collection_points) > 0:
                    return int(collection_points)
        except Exception as error:
            logger.warning(
                "memory_documents_count_resolution_failed collection=%s error=%s",
                collection_name,
                error,
            )

        return int(fallback_count or 0)

    def _get_semantic_store(self) -> Any | None:
        global _QDRANT_STORE_CACHE
        if _QDRANT_STORE_CACHE is not None:
            return _QDRANT_STORE_CACHE
        if QdrantStore is None:
            return None
        try:
            _QDRANT_STORE_CACHE = QdrantStore(check_compatibility=False, mode="host")
            return _QDRANT_STORE_CACHE
        except Exception:
            return None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        if not text:
            return set()
        return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 2}

    @staticmethod
    def _overlap_score(query_tokens: set[str], target_tokens: set[str]) -> float:
        if not query_tokens or not target_tokens:
            return 0.0
        overlap = query_tokens.intersection(target_tokens)
        if not overlap:
            return 0.0
        return len(overlap) / len(query_tokens)


def setup_memory(config: dict[str, Any]) -> dict[str, Any]:
    """
    Initialize memory storage based on configuration.

    Args:
        config: Configuration dictionary containing storage type and settings

    Returns:
        Dictionary with initialization status
    """
    try:
        storage_type = config.get("type", "json")

        if storage_type == "json":
            file_path = config.get("file_path", ".hordeforge_data/memory.json")
            storage = get_storage_backend(backend_type=storage_type, file_path=file_path)
        elif storage_type == "postgres":
            connection_string = config.get("connection_string") or os.getenv(
                "HORDEFORGE_POSTGRES_CONNECTION_STRING", ""
            )
            storage = get_storage_backend(
                backend_type=storage_type, connection_string=connection_string
            )
        else:
            return {"status": "failed", "error": f"Unsupported storage type: {storage_type}"}

        # Store the storage instance in the MemoryAgent class for later use
        MemoryAgent.storage = storage

        return {"status": "ready"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def retrieve_context(context_id: str) -> dict[str, Any]:
    """
    Retrieve context from memory storage.

    Args:
        context_id: Unique identifier for the context to retrieve

    Returns:
        Dictionary with retrieval status and context data
    """
    try:
        if MemoryAgent.storage is None:
            # Initialize storage with default settings if not already set up
            result = setup_memory({"type": "json"})
            if result["status"] != "ready":
                return {"status": "not_found", "error": "Failed to initialize storage"}

        # Read all items from storage
        all_items = MemoryAgent.storage.read_all()

        # Find the item with the matching context_id
        for item in all_items:
            if item.get("context_id") == context_id:
                return {"status": "success", "context": item}

        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def store_context(context: dict[str, Any]) -> dict[str, Any]:
    """
    Store context in memory storage.

    Args:
        context: Context data to store

    Returns:
        Dictionary with storage status and context ID
    """
    try:
        if not context:
            return {"status": "failed", "error": "Empty context provided"}

        if MemoryAgent.storage is None:
            # Initialize storage with default settings if not already set up
            result = setup_memory({"type": "json"})
            if result["status"] != "ready":
                return {"status": "failed", "error": "Failed to initialize storage"}

        # Generate a context ID if not provided
        import uuid

        context_id = context.get("context_id", str(uuid.uuid4()))
        context["context_id"] = context_id

        # Read existing items
        all_items = MemoryAgent.storage.read_all()

        # Check if context with this ID already exists and update it, otherwise add new
        updated = False
        for i, item in enumerate(all_items):
            if item.get("context_id") == context_id:
                all_items[i] = context
                updated = True
                break

        if not updated:
            all_items.append(context)

        # Write all items back to storage
        MemoryAgent.storage.write_all(all_items)

        return {"status": "success", "context_id": context_id}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
