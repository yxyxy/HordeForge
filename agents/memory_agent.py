from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class MemoryAgent:
    name = "memory_agent"
    description = "Creates an initial downstream-ready memory state."

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
