from __future__ import annotations

import json
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
except Exception:
    QdrantStore = None

_QDRANT_STORE_CACHE: dict[str, Any] = {}
logger = logging.getLogger(__name__)


class MemoryType(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "Creates a downstream-ready memory state, retrieves relevant memory, and persists memory entries."
    storage: StorageBackend | None = None

    def __init__(self):
        self.storage = MemoryAgent.storage

    def run(self, context: dict[str, Any]) -> dict:
        mode = self._detect_memory_mode(context)
        repository_metadata = (
            get_artifact_from_context(
                context, "repository_data", preferred_steps=["repo_connector"]
            )
            or get_artifact_from_context(
                context, "repository_metadata", preferred_steps=["repo_connector"]
            )
            or {}
        )
        rag_index = (
            get_artifact_from_context(context, "rag_index", preferred_steps=["rag_initializer"])
            or {}
        )
        query = self._resolve_query(context.get("query"), context)
        if mode == "retrieve":
            return self._run_retrieve_mode(
                query=query, rag_index=rag_index, repository_metadata=repository_metadata
            )
        if mode == "write":
            return self._run_write_mode(
                context=context, repository_metadata=repository_metadata, rag_index=rag_index
            )
        return self._run_seed_mode(repository_metadata=repository_metadata, rag_index=rag_index)

    def _detect_memory_mode(self, context: dict[str, Any]) -> str:
        if context.get("memory_mode") in {"retrieve", "write", "seed"}:
            return str(context["memory_mode"])
        write_intent = (
            context.get("task_description") is not None
            or context.get("result") is not None
            or context.get("code_patch") is not None
            or context.get("final_code_patch") is not None
            or context.get("fixed_code_patch") is not None
        )
        if write_intent:
            return "write"
        if self._resolve_query(context.get("query"), context).strip():
            return "retrieve"
        return "seed"

    def _run_retrieve_mode(
        self, *, query: str, rag_index: dict[str, Any], repository_metadata: dict[str, Any]
    ) -> dict:
        if not query.strip():
            return build_agent_result(
                status="BLOCKED",
                artifact_type="memory_context",
                artifact_content={
                    "query": "",
                    "matches": [],
                    "quality_signals": {
                        "memory_mode": "retrieve",
                        "retrieval_strategy": "none",
                        "semantic_store_available": False,
                        "retrieval_confidence": "low",
                    },
                },
                reason="Memory retrieval requested but query could not be resolved.",
                confidence=0.99,
                logs=["Missing or empty memory retrieval query."],
                next_actions=["provide_query"],
            )
        ctx = self._build_memory_context(query.strip(), rag_index)
        ctx["repository"] = {
            "owner": repository_metadata.get("owner", "unknown"),
            "repo_name": repository_metadata.get("repo_name", "unknown"),
            "full_name": repository_metadata.get("full_name", "unknown"),
        }
        quality = ctx.get("quality_signals", {})
        confidence = {"high": 0.84, "medium": 0.76, "low": 0.68}.get(
            quality.get("retrieval_confidence", "low"), 0.68
        )
        return build_agent_result(
            status="SUCCESS" if ctx.get("matches") else "PARTIAL_SUCCESS",
            artifact_type="memory_context",
            artifact_content=ctx,
            reason="Memory context retrieved from available indexes.",
            confidence=confidence,
            logs=[
                "Memory retrieval mode: retrieve",
                f"Memory retrieval query received: {query.strip()[:120]}",
                f"Memory retrieval matches: {len(ctx.get('matches', []))}.",
                f"Retrieval strategy: {quality.get('retrieval_strategy', 'unknown')}.",
            ],
            next_actions=["code_generator", "architecture_planner"],
        )

    def _run_seed_mode(
        self, *, repository_metadata: dict[str, Any], rag_index: dict[str, Any]
    ) -> dict:
        docs_count = self._resolve_documents_count(
            rag_index=rag_index if isinstance(rag_index, dict) else {},
            collection_name=str(rag_index.get("collection_name") or "repo_chunks")
            if isinstance(rag_index, dict)
            else "repo_chunks",
            fallback_count=len(rag_index.get("documents", []))
            if isinstance(rag_index, dict) and isinstance(rag_index.get("documents"), list)
            else 0,
        )
        semantic_store_available = (
            self._get_semantic_store(mode=self._resolve_vector_store_mode()) is not None
        )
        ready = bool(repository_metadata and (rag_index or docs_count > 0))
        artifact = {
            "schema_version": "1.1",
            "repository": {
                "owner": repository_metadata.get("owner", "unknown"),
                "repo_name": repository_metadata.get("repo_name", "unknown"),
                "full_name": repository_metadata.get("full_name", "unknown"),
            },
            "knowledge": {
                "documents_count": docs_count,
                "index_id": rag_index.get("index_id", "rag_index_missing")
                if isinstance(rag_index, dict)
                else "rag_index_missing",
                "collection_name": str(rag_index.get("collection_name") or "repo_chunks")
                if isinstance(rag_index, dict)
                else "repo_chunks",
            },
            "events": [{"type": "memory_initialized", "source": "memory_agent"}],
            "ready_for_downstream": ready,
            "quality_signals": {
                "memory_mode": "seed",
                "semantic_store_available": semantic_store_available,
                "documents_count_source": "rag_index_or_store",
                "retrieval_confidence": "medium" if ready else "low",
            },
            "plan_provenance": {"source": "repository_metadata_and_rag_index", "rebuilt": False},
        }
        return build_agent_result(
            status="SUCCESS" if ready else "PARTIAL_SUCCESS",
            artifact_type="memory_context",
            artifact_content=artifact,
            reason="Memory state prepared from repository metadata and docs index.",
            confidence=0.86 if ready else 0.7,
            logs=[
                "Initial memory state prepared.",
                f"Repository metadata present: {bool(repository_metadata)}.",
                f"RAG index present: {bool(rag_index)}.",
                f"Semantic store available: {semantic_store_available}.",
            ],
            next_actions=["architecture_evaluator", "test_analyzer"],
        )

    def _run_write_mode(
        self,
        *,
        context: dict[str, Any],
        repository_metadata: dict[str, Any],
        rag_index: dict[str, Any],
    ) -> dict:
        task_description = str(context.get("task_description", "")).strip()
        result_payload = context.get("result")
        code_patch = context.get("code_patch")

        # Fallback: try to extract from nested structures if direct values are missing
        if not task_description or result_payload is None or not isinstance(code_patch, dict):
            task_description = self._extract_task_description_fallback(context, task_description)
            result_payload = self._extract_result_fallback(context, result_payload)
            code_patch = self._extract_code_patch_fallback(context, code_patch)

        if not task_description or result_payload is None or not isinstance(code_patch, dict):
            return build_agent_result(
                status="BLOCKED",
                artifact_type="memory_write_result",
                artifact_content={
                    "schema_version": "1.1",
                    "quality_signals": {"memory_mode": "write", "write_persisted": False},
                },
                reason="Memory write requested but task_description, result, or code_patch is missing.",
                confidence=0.99,
                logs=["Write mode requires task_description, result, and code_patch."],
                next_actions=["provide_memory_write_payload"],
            )
        fallback_result = (
            isinstance(result_payload, dict)
            and str(result_payload.get("source", "")).strip() == "memory_agent_fallback"
        )
        fallback_patch = (
            isinstance(code_patch, dict)
            and str(code_patch.get("note", "")).strip() == "fallback_empty_patch"
        )
        files = code_patch.get("files") if isinstance(code_patch, dict) else None
        patch_has_files = isinstance(files, list) and len(files) > 0
        if fallback_result or fallback_patch or not patch_has_files:
            return build_agent_result(
                status="PARTIAL_SUCCESS",
                artifact_type="memory_write_result",
                artifact_content={
                    "schema_version": "1.1",
                    "task_description": task_description,
                    "result": result_payload,
                    "code_patch": code_patch,
                    "event_type": "memory_write",
                    "context_id": None,
                    "quality_signals": {
                        "memory_mode": "write",
                        "write_persisted": False,
                        "semantic_store_available": self._get_semantic_store(
                            mode=self._resolve_vector_store_mode()
                        )
                        is not None,
                    },
                    "plan_provenance": {"source": "write_request", "rebuilt": True},
                },
                reason="Memory write skipped because payload is incomplete or fallback-generated.",
                confidence=0.9,
                logs=[
                    "Memory write skipped: incomplete payload.",
                    f"Fallback result used: {fallback_result}.",
                    f"Fallback patch used: {fallback_patch}.",
                    f"Patch has files: {patch_has_files}.",
                ],
                next_actions=["provide_memory_write_payload"],
            )
        payload = {
            "task_description": task_description,
            "repository": repository_metadata.get("full_name", "unknown"),
            "result": result_payload,
            "code_patch": code_patch,
            "rag_index_id": rag_index.get("index_id") if isinstance(rag_index, dict) else None,
            "entry_type": "task",
        }
        store_result = store_context(payload)
        persisted = store_result.get("status") == "success"
        artifact = {
            "schema_version": "1.1",
            "task_description": task_description,
            "result": result_payload,
            "code_patch": code_patch,
            "event_type": "memory_write",
            "context_id": store_result.get("context_id"),
            "quality_signals": {
                "memory_mode": "write",
                "write_persisted": persisted,
                "semantic_store_available": self._get_semantic_store(
                    mode=self._resolve_vector_store_mode()
                )
                is not None,
            },
            "plan_provenance": {"source": "write_request", "rebuilt": False},
        }
        logs = [
            "Memory write operation attempted.",
            f"Repository metadata present: {bool(repository_metadata)}.",
            f"RAG index present: {bool(rag_index)}.",
        ]
        if store_result.get("error"):
            logs.append(f"Memory write error: {store_result['error']}")
        return build_agent_result(
            status="SUCCESS" if persisted else "PARTIAL_SUCCESS",
            artifact_type="memory_write_result",
            artifact_content=artifact,
            reason="Memory write operation completed successfully."
            if persisted
            else "Memory write request handled but persistence failed.",
            confidence=0.88 if persisted else 0.72,
            logs=logs,
            next_actions=["pr_merge_agent"] if persisted else ["check_memory_storage"],
        )

    def _resolve_query(self, raw_query: Any, context: dict[str, Any]) -> str:
        if isinstance(raw_query, str):
            query = raw_query.strip()
            if query and "{{" not in query and "}}" not in query:
                return query
        issue = context.get("issue")
        if not isinstance(issue, dict):
            return ""
        parts = []
        for field in ("title", "body", "comments_context"):
            value = issue.get(field)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if isinstance(issue.get("comments"), list):
            bodies = [
                item.get("body", "").strip()
                for item in issue["comments"]
                if isinstance(item, dict)
                and isinstance(item.get("body"), str)
                and item.get("body").strip()
            ]
            if bodies:
                parts.append("\n".join(bodies[:10]))
        return "\n".join(parts)

    def _build_memory_context(self, query: str, rag_index: dict[str, Any]) -> dict[str, Any]:
        persisted_memory_matches = self._memory_store_search(query=query, limit=8)
        semantic_matches = self._semantic_search(query=query, rag_index=rag_index, limit=8)
        docs = rag_index.get("documents") if isinstance(rag_index, dict) else []
        if not isinstance(docs, list):
            docs = []
        query_tokens = self._tokenize(query)
        lexical_matches = []
        for item in docs:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            summary = str(item.get("summary", "")).strip()
            content = str(item.get("content", "")).strip()
            score = self._overlap_score(query_tokens, self._tokenize(f"{path} {summary} {content}"))
            if score > 0:
                lexical_matches.append(
                    {
                        "path": path or "unknown",
                        "summary": summary or content[:200],
                        "score": float(score),
                        "source": "lexical",
                    }
                )
        lexical_matches.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        merged = {}
        for item in persisted_memory_matches + semantic_matches + lexical_matches:
            key = f"{item.get('path')}|{item.get('summary')}"
            if key not in merged or float(item.get("score", 0.0)) > float(
                merged[key].get("score", 0.0)
            ):
                merged[key] = item
        ranked = sorted(merged.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)
        if persisted_memory_matches and (semantic_matches or lexical_matches):
            strategy = "hybrid_with_memory"
        elif persisted_memory_matches:
            strategy = "memory_store"
        elif semantic_matches and lexical_matches:
            strategy = "hybrid"
        elif semantic_matches:
            strategy = "semantic"
        else:
            strategy = "lexical_fallback"
        confidence = (
            "high"
            if persisted_memory_matches or semantic_matches
            else "medium"
            if lexical_matches
            else "low"
        )
        collection = (
            str(rag_index.get("collection_name") or "repo_chunks")
            if isinstance(rag_index, dict)
            else "repo_chunks"
        )
        return {
            "query": query,
            "matches": ranked[:5],
            "documents_count": self._resolve_documents_count(
                rag_index=rag_index if isinstance(rag_index, dict) else {},
                collection_name=collection,
                fallback_count=len(docs),
            ),
            "collection_name": collection,
            "quality_signals": {
                "memory_mode": "retrieve",
                "semantic_store_available": self._get_semantic_store(
                    mode=self._resolve_vector_store_mode()
                )
                is not None,
                "memory_store_matches_count": len(persisted_memory_matches),
                "semantic_matches_count": len(semantic_matches),
                "lexical_matches_count": len(lexical_matches),
                "documents_count_source": "rag_index_or_store",
                "retrieval_strategy": strategy,
                "retrieval_confidence": confidence,
            },
            "plan_provenance": {"source": "query_and_rag_index", "rebuilt": False},
        }

    def _memory_store_search(self, *, query: str, limit: int) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if MemoryAgent.storage is None:
            backend_type = str(os.getenv("HORDEFORGE_STORAGE_BACKEND", "json") or "json").strip()
            if setup_memory({"type": backend_type}).get("status") != "ready":
                return []
        if MemoryAgent.storage is None:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        matches: list[dict[str, Any]] = []
        try:
            for item in MemoryAgent.storage.read_all():
                if not isinstance(item, dict):
                    continue
                task_description = str(item.get("task_description", "")).strip()
                result_payload = item.get("result")
                code_patch = item.get("code_patch")
                searchable_blob = " ".join(
                    [
                        task_description,
                        str(item.get("repository", "")),
                        json.dumps(result_payload, ensure_ascii=False, default=str),
                        json.dumps(code_patch, ensure_ascii=False, default=str),
                    ]
                )
                score = self._overlap_score(query_tokens, self._tokenize(searchable_blob))
                if score <= 0:
                    continue
                context_id = str(item.get("context_id", "")).strip()
                summary = task_description or str(result_payload)[:220]
                path = f"memory://{context_id}" if context_id else "memory://entry"
                matches.append(
                    {
                        "path": path,
                        "summary": summary[:220],
                        "score": float(score),
                        "source": "memory_store",
                        "context_id": context_id or None,
                    }
                )
        except Exception as error:
            logger.warning("memory_store_search_failed error=%s", error)
            return []

        matches.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return matches[: max(1, int(limit))]

    def _semantic_search(self, *, query: str, rag_index: dict[str, Any], limit: int):
        if QdrantStore is None:
            return []
        collection = (
            str(rag_index.get("collection_name") or "repo_chunks").strip()
            if isinstance(rag_index, dict)
            else "repo_chunks"
        )
        try:
            store = self._get_semantic_store(mode=self._resolve_vector_store_mode())
            if store is None:
                return []
            vectors = store.embed_text([query])
            if not vectors:
                return []
            results = store.search(
                collection_name=collection or "repo_chunks",
                query_vector=vectors[0],
                limit=max(1, int(limit)),
            )
        except Exception as error:
            logger.warning(
                "memory_semantic_search_failed collection=%s error=%s", collection, error
            )
            return []
        matches = []
        for result in results:
            if not isinstance(result, dict):
                continue
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            text = str(payload.get("text", "")).strip()
            path = str(payload.get("file_path", "")).strip() or "unknown"
            summary = (
                text[:220]
                if text
                else str(payload.get("symbol_name", "")).strip() or "semantic_match"
            )
            score = float(result.get("score", 0.0) or 0.0)
            if score > 0:
                matches.append(
                    {"path": path, "summary": summary, "score": score, "source": "semantic"}
                )
        return matches

    def _resolve_documents_count(
        self, *, rag_index: dict[str, Any], collection_name: str, fallback_count: int
    ) -> int:
        try:
            count = int(
                (rag_index.get("documents_count") if isinstance(rag_index, dict) else 0) or 0
            )
        except Exception:
            count = 0
        if count > 0:
            return count
        try:
            store = self._get_semantic_store(mode=self._resolve_vector_store_mode())
            if store is not None and hasattr(store, "get_collection_points_count"):
                points = store.get_collection_points_count(collection_name)
                if points is not None and int(points) > 0:
                    return int(points)
        except Exception as error:
            logger.warning(
                "memory_documents_count_resolution_failed collection=%s error=%s",
                collection_name,
                error,
            )
        return int(fallback_count or 0)

    def _resolve_vector_store_mode(self) -> str:
        return str(os.getenv("HORDEFORGE_VECTOR_STORE_MODE", "auto") or "auto").strip() or "auto"

    def _get_semantic_store(self, *, mode: str):
        if mode in _QDRANT_STORE_CACHE:
            return _QDRANT_STORE_CACHE[mode]
        if QdrantStore is None:
            return None
        try:
            store = QdrantStore(check_compatibility=False, mode=mode)
            _QDRANT_STORE_CACHE[mode] = store
            return store
        except Exception:
            return None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return (
            {t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(t) > 2} if text else set()
        )

    @staticmethod
    def _overlap_score(query_tokens: set[str], target_tokens: set[str]) -> float:
        if not query_tokens or not target_tokens:
            return 0.0
        overlap = query_tokens.intersection(target_tokens)
        return len(overlap) / len(query_tokens) if overlap else 0.0

    @staticmethod
    def _extract_task_description_fallback(context: dict[str, Any], current: str) -> str:
        """Try to extract task description from context if not directly available."""
        if current:
            return current

        # Try issue context
        issue = context.get("issue")
        if isinstance(issue, dict):
            title = issue.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
            body = issue.get("body")
            if isinstance(body, str) and body.strip():
                return body.strip()[:500]

        # Try spec context
        spec = context.get("spec")
        if isinstance(spec, dict):
            summary = spec.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip()

        return current

    @staticmethod
    def _extract_result_fallback(context: dict[str, Any], current: Any) -> Any:
        """Try to extract result from context if not directly available."""
        if current is not None:
            return current

        # Try review_result
        review = context.get("review_result")
        if isinstance(review, dict):
            return review

        # Try test_results
        test_results = context.get("test_results")
        if isinstance(test_results, dict):
            return test_results

        # Create minimal result from context
        return {
            "status": "completed",
            "source": "memory_agent_fallback",
            "context_keys": list(context.keys())[:10],
        }

    @staticmethod
    def _extract_code_patch_fallback(context: dict[str, Any], current: Any) -> Any:
        """Try to extract code patch from context if not directly available."""
        if isinstance(current, dict):
            return current

        # Try final_code_patch
        final_patch = context.get("final_code_patch")
        if isinstance(final_patch, dict):
            return final_patch

        # Try fixed_code_patch
        fixed_patch = context.get("fixed_code_patch")
        if isinstance(fixed_patch, dict):
            return fixed_patch

        # Try to get from code_generator result
        code_gen = context.get("code_generator")
        if isinstance(code_gen, dict):
            patch = code_gen.get("code_patch")
            if isinstance(patch, dict):
                return patch

        # Create minimal patch
        return {
            "files": [],
            "schema_version": "1.0",
            "note": "fallback_empty_patch",
        }


def setup_memory(config: dict[str, Any]) -> dict[str, Any]:
    try:
        storage_type = config.get("type", "json")
        if storage_type == "json":
            storage = get_storage_backend(
                backend_type=storage_type,
                file_path=config.get("file_path", ".hordeforge_data/memory.json"),
            )
        elif storage_type == "postgres":
            storage = get_storage_backend(
                backend_type=storage_type,
                connection_string=config.get("connection_string")
                or os.getenv("HORDEFORGE_POSTGRES_CONNECTION_STRING", ""),
            )
        else:
            return {"status": "failed", "error": f"Unsupported storage type: {storage_type}"}
        MemoryAgent.storage = storage
        return {"status": "ready"}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def retrieve_context(context_id: str) -> dict[str, Any]:
    try:
        backend_type = str(os.getenv("HORDEFORGE_STORAGE_BACKEND", "json") or "json").strip()
        if (
            MemoryAgent.storage is None
            and setup_memory({"type": backend_type}).get("status") != "ready"
        ):
            return {"status": "not_found", "error": "Failed to initialize storage"}
        for item in MemoryAgent.storage.read_all():
            if item.get("context_id") == context_id:
                return {"status": "success", "context": item}
        return {"status": "not_found"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def store_context(context: dict[str, Any]) -> dict[str, Any]:
    try:
        if not context:
            return {"status": "failed", "error": "Empty context provided"}
        backend_type = str(os.getenv("HORDEFORGE_STORAGE_BACKEND", "json") or "json").strip()
        if (
            MemoryAgent.storage is None
            and setup_memory({"type": backend_type}).get("status") != "ready"
        ):
            return {"status": "failed", "error": "Failed to initialize storage"}
        import uuid

        context_id = context.get("context_id", str(uuid.uuid4()))
        context["context_id"] = context_id
        items = MemoryAgent.storage.read_all()
        for i, item in enumerate(items):
            if item.get("context_id") == context_id:
                items[i] = context
                break
        else:
            items.append(context)
        MemoryAgent.storage.write_all(items)
        return {"status": "success", "context_id": context_id}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
