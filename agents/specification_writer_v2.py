from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import build_spec_prompt, get_llm_wrapper


class EnhancedSpecificationWriter(BaseAgent):
    """Production-ready specification writer with LLM support."""

    name = "specification_writer"
    description = "Builds feature spec from DoD and upstream planning context."

    def run(self, context: dict[str, Any]) -> dict:
        # Gather inputs from context
        upstream_spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["architecture_planner"],
            )
            or {}
        )
        dod = (
            get_artifact_from_context(
                context,
                "dod",
                preferred_steps=["dod_extractor"],
            )
            or {}
        )
        rag_context = (
            get_artifact_from_context(
                context,
                "rag_context",
                preferred_steps=["rag_retriever"],
            )
            or {}
        )
        rules_payload = context.get("rules") if isinstance(context.get("rules"), dict) else {}
        rule_documents = (
            rules_payload.get("documents")
            if isinstance(rules_payload.get("documents"), dict)
            else {}
        )

        # Extract requirements from all sources
        requirements = []
        if isinstance(upstream_spec.get("requirements"), list):
            requirements.extend(
                item
                for item in upstream_spec["requirements"]
                if isinstance(item, str) and item.strip()
            )
        if isinstance(dod.get("acceptance_criteria"), list):
            requirements.extend(
                item
                for item in dod["acceptance_criteria"]
                if isinstance(item, str) and item.strip()
            )
        if not requirements:
            requirements = ["Implement feature behavior from issue context."]

        # Add RAG context guidance
        rag_sources = rag_context.get("sources")
        if isinstance(rag_sources, list):
            for source in rag_sources:
                source_ref = str(source).strip()
                if source_ref:
                    requirements.append(f"Align implementation with guidance from {source_ref}.")

        # Add security rules
        security_rules = rule_documents.get("security")
        if isinstance(security_rules, dict):
            security_source = str(security_rules.get("source_path", "")).strip()
            if security_source:
                requirements.append(f"Apply security constraints from {security_source}.")

        # Deduplicate
        deduped: list[str] = []
        seen: set[str] = set()
        for item in requirements:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        summary = upstream_spec.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = "Feature specification generated from DoD."

        # Try LLM-enhanced generation
        llm_spec = None
        llm_error = None
        use_llm = context.get("use_llm", True)  # Default to using LLM if available

        if use_llm:
            try:
                llm = get_llm_wrapper()
                if llm is not None:
                    # Build context for LLM
                    llm_context = {
                        "has_upstream_spec": bool(upstream_spec),
                        "has_dod": bool(dod),
                        "rag_sources_count": len(rag_sources)
                        if isinstance(rag_sources, list)
                        else 0,
                        "rules_documents": list(rule_documents.keys()),
                    }
                    prompt = build_spec_prompt(summary, deduped, llm_context)
                    response = llm.complete(prompt)
                    llm.close()

                    # Parse JSON response
                    import json

                    llm_spec = json.loads(response)
            except Exception as e:
                llm_error = str(e)

        # Build final spec
        if llm_spec and isinstance(llm_spec, dict):
            # Use LLM-generated spec as base
            spec = {
                "schema_version": "2.0",
                "summary": llm_spec.get("summary", summary),
                "requirements": llm_spec.get("requirements", deduped),
                "technical_notes": llm_spec.get("technical_notes", []),
                "file_changes": llm_spec.get("file_changes", []),
                "llm_enhanced": True,
            }
            reason = "Spec generated with LLM enhancement."
            confidence = 0.95
        else:
            # Fallback to deterministic generation
            spec = self._build_deterministic_spec(
                summary=summary,
                requirements=deduped,
                rag_sources=rag_sources,
                rule_documents=rule_documents,
            )
            reason = (
                "Deterministic spec generated (LLM unavailable)."
                if llm_error
                else "Feature spec generated from available artifacts."
            )
            confidence = 0.9 if llm_error else 0.9

        # Build notes
        notes = [
            f"requirements_count={len(spec['requirements'])}",
        ]
        if isinstance(rag_sources, list):
            normalized_sources = [str(item).strip() for item in rag_sources if str(item).strip()]
            notes.append(f"rag_sources={len(normalized_sources)}")
        rules_version = str(rules_payload.get("version", "")).strip()
        if rules_version:
            notes.append(f"rules_version={rules_version}")
            notes.append(f"rules_documents={len(rule_documents)}")
        if llm_error:
            notes.append(f"llm_error={llm_error[:50]}")

        spec["notes"] = notes

        return build_agent_result(
            status="SUCCESS",
            artifact_type="spec",
            artifact_content=spec,
            reason=reason,
            confidence=confidence,
            logs=["Specification writer produced spec artifact."],
            next_actions=["task_decomposer"],
        )

    def _build_deterministic_spec(
        self,
        summary: str,
        requirements: list[str],
        rag_sources: list | None,
        rule_documents: dict,
    ) -> dict:
        """Build deterministic spec as fallback."""
        # Analyze requirements to infer file changes
        file_changes = []
        req_text = " ".join(requirements).lower()

        # Common patterns
        if "api" in req_text or "endpoint" in req_text:
            file_changes.append(
                {
                    "path": "src/api/routes.py",
                    "change_type": "modify",
                    "description": "API endpoint definitions",
                }
            )
        if "model" in req_text or "database" in req_text:
            file_changes.append(
                {"path": "src/models.py", "change_type": "modify", "description": "Data models"}
            )
        if "test" in req_text:
            file_changes.append(
                {
                    "path": "tests/test_feature.py",
                    "change_type": "create",
                    "description": "Feature tests",
                }
            )

        technical_notes = [
            "Follow existing code patterns in the repository.",
            "Ensure backward compatibility where possible.",
        ]
        if rule_documents:
            technical_notes.append(f"Apply rules from: {', '.join(rule_documents.keys())}")

        return {
            "schema_version": "2.0",
            "summary": summary,
            "requirements": requirements,
            "technical_notes": technical_notes,
            "file_changes": file_changes,
            "llm_enhanced": False,
        }
