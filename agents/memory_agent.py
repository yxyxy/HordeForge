from __future__ import annotations

import os
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from storage.backends import StorageBackend, get_storage_backend


class MemoryType(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "Creates an initial downstream-ready memory state."

    def __init__(self):
        self.storage: StorageBackend | None = None

    def run(self, context: dict[str, Any]) -> dict:
        repository_metadata = (
            get_artifact_from_context(
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

        has_repo = bool(repository_metadata)
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
