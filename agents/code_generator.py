from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class CodeGenerator:
    name = "code_generator"
    description = "Generates deterministic dry-run code patch from tests/subtasks."

    def run(self, context: dict[str, Any]) -> dict:
        tests = (
            get_artifact_from_context(
                context,
                "tests",
                preferred_steps=["test_generator"],
            )
            or {}
        )
        subtasks = (
            get_artifact_from_context(
                context,
                "subtasks",
                preferred_steps=["task_decomposer"],
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

        test_cases = tests.get("test_cases")
        test_count = len(test_cases) if isinstance(test_cases, list) else 0
        items = subtasks.get("items")
        subtask_count = len(items) if isinstance(items, list) else 0
        rag_sources = rag_context.get("sources")
        rag_source_count = len(rag_sources) if isinstance(rag_sources, list) else 0
        rules_documents = rules_payload.get("documents")
        rule_doc_count = len(rules_documents) if isinstance(rules_documents, dict) else 0
        rules_version = str(rules_payload.get("version", "")).strip()

        patch = {
            "schema_version": "1.0",
            "files": [
                {
                    "path": "src/feature_impl.py",
                    "diff": "+# deterministic MVP patch placeholder\n",
                }
            ],
            "decisions": [
                f"subtasks={subtask_count}",
                f"tests={test_count}",
                f"rag_sources={rag_source_count}",
                f"rules_documents={rule_doc_count}",
                f"rules_version={rules_version or 'none'}",
                "dry_run_patch=true",
            ],
            "dry_run": True,
            "expected_failures": 1 if test_count > 0 else 0,
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason="Dry-run patch generated to satisfy MVP development flow.",
            confidence=0.87,
            logs=["Code generator produced deterministic dry-run patch."],
            next_actions=["test_runner", "fix_agent"],
        )
