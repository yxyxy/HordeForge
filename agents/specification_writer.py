from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class SpecificationWriter:
    name = "specification_writer"
    description = "Builds feature spec from DoD and upstream planning context."

    def run(self, context: dict[str, Any]) -> dict:
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

        rag_sources = rag_context.get("sources")
        if isinstance(rag_sources, list):
            for source in rag_sources:
                source_ref = str(source).strip()
                if source_ref:
                    requirements.append(f"Align implementation with guidance from {source_ref}.")
        security_rules = rule_documents.get("security")
        if isinstance(security_rules, dict):
            security_source = str(security_rules.get("source_path", "")).strip()
            if security_source:
                requirements.append(f"Apply security constraints from {security_source}.")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in requirements:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        summary = upstream_spec.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = "Feature specification generated from DoD."

        notes = [
            "Deterministic MVP output.",
            f"requirements_count={len(deduped)}",
        ]
        if isinstance(rag_sources, list):
            normalized_sources = [str(item).strip() for item in rag_sources if str(item).strip()]
            notes.append(f"rag_sources={len(normalized_sources)}")
        rules_version = str(rules_payload.get("version", "")).strip()
        if rules_version:
            notes.append(f"rules_version={rules_version}")
            notes.append(f"rules_documents={len(rule_documents)}")

        spec = {
            "schema_version": "1.0",
            "summary": summary,
            "requirements": deduped,
            "notes": notes,
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="spec",
            artifact_content=spec,
            reason="Feature spec generated from available DoD/planning artifacts.",
            confidence=0.9,
            logs=["Specification writer produced schema-ready spec artifact."],
            next_actions=["task_decomposer"],
        )
