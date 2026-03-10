from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class ArchitecturePlanner:
    name = "architecture_planner"
    description = "Creates technical specification and task plan based on DoD."

    def run(self, context: dict[str, Any]) -> dict:
        # Extract DoD from context
        dod = (
            get_artifact_from_context(
                context,
                "dod",
                preferred_steps=["dod_extractor"],
            )
            or {}
        )

        # Extract repository context
        repository = context.get("repository", {})

        # Extract RAG context for additional guidance
        rag_context = (
            get_artifact_from_context(
                context,
                "rag_context",
                preferred_steps=["rag_retriever"],
            )
            or {}
        )

        # Build technical specification
        requirements = []

        # Extract acceptance criteria from DoD
        acceptance_criteria = dod.get("acceptance_criteria")
        if isinstance(acceptance_criteria, list):
            requirements.extend(
                item
                for item in acceptance_criteria
                if isinstance(item, str) and item.strip()
            )

        # Extract technical requirements from repository context
        if isinstance(repository, dict):
            repo_name = repository.get("full_name")
            if repo_name:
                requirements.append(f"Implement feature for repository {repo_name}.")

            default_branch = repository.get("default_branch")
            if default_branch:
                requirements.append(f"Target branch: {default_branch}.")

        # Add RAG-based guidance
        rag_sources = rag_context.get("sources")
        if isinstance(rag_sources, list):
            for source in rag_sources[:3]:  # Limit to top 3 sources
                source_ref = str(source).strip()
                if source_ref:
                    requirements.append(f"Consider guidance from {source_ref}.")

        # If no requirements, provide default
        if not requirements:
            requirements = ["Implement feature based on provided specification."]

        # Deduplicate requirements
        deduped: list[str] = []
        seen: set[str] = set()
        for item in requirements:
            normalized = item.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)

        # Generate summary
        summary = "Technical specification generated from DoD and context."
        if dod.get("title"):
            summary = f"Architecture plan for: {dod.get('title')}"

        # Build technical decisions
        decisions = []
        if repository.get("language"):
            decisions.append({
                "reason": f"Primary language detected: {repository.get('language')}",
                "confidence": 0.85,
            })
        if rag_sources:
            decisions.append({
                "reason": f"Using {len(rag_sources)} RAG sources for context",
                "confidence": 0.8,
            })

        # Build spec artifact
        spec_artifact = {
            "schema_version": "1.0",
            "summary": summary,
            "requirements": deduped,
            "repository": {
                "full_name": repository.get("full_name") if isinstance(repository, dict) else None,
                "default_branch": repository.get("default_branch") if isinstance(repository, dict) else None,
                "language": repository.get("language") if isinstance(repository, dict) else None,
            },
            "notes": [
                f"requirements_count={len(deduped)}",
                f"rag_sources={len(rag_sources) if isinstance(rag_sources, list) else 0}",
            ],
        }

        return build_agent_result(
            status="SUCCESS",
            artifact_type="spec",
            artifact_content=spec_artifact,
            reason="Technical specification generated from DoD and context.",
            confidence=0.9,
            logs=[
                f"ArchitecturePlanner generated spec with {len(deduped)} requirements.",
                f"Repository: {repository.get('full_name') if isinstance(repository, dict) else 'unknown'}",
            ],
            next_actions=["specification_writer", "task_decomposer"],
        )
