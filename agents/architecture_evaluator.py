from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context


class ArchitectureEvaluator(BaseAgent):
    name = "architecture_evaluator"
    description = "Generates a baseline deterministic architecture report."

    def run(self, context: dict[str, Any]) -> dict:
        repository_metadata = get_artifact_from_context(
            context,
            "repository_metadata",
            preferred_steps=["repo_connector"],
        )
        has_repo = bool(repository_metadata)

        full_name = "unknown"
        if isinstance(repository_metadata, dict):
            full_name = repository_metadata.get("full_name", "unknown")

        report = {
            "target": full_name,
            "findings": [
                "MVP runtime is orchestrator-driven.",
                "Agent contracts are validated by runtime schema validator.",
            ],
            "risks": [] if has_repo else ["Repository metadata is missing; analysis is generic."],
            "recommendations": [
                "Add integration tests for init/feature/ci_fix pipelines.",
                "Promote deterministic stubs to production integrations.",
            ],
        }
        return build_agent_result(
            status="SUCCESS" if has_repo else "PARTIAL_SUCCESS",
            artifact_type="architecture_report",
            artifact_content=report,
            reason="Baseline architecture report generated for initialization flow.",
            confidence=0.84 if has_repo else 0.66,
            logs=["Architecture evaluation completed in MVP deterministic mode."],
            next_actions=["pipeline_initializer"],
        )
