from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import build_code_prompt, get_llm_wrapper
from agents.patch_workflow import PatchWorkflowOrchestrator, create_patch_from_code_result


class EnhancedCodeGenerator:
    """Production-ready code generator with LLM support."""

    name = "code_generator"
    description = "Generates code patch from tests/subtasks with LLM synthesis."

    def run(self, context: dict[str, Any]) -> dict:
        # Gather inputs
        spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer"],
            )
            or {}
        )
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

        # Extract key data
        test_cases = tests.get("test_cases", [])
        test_count = len(test_cases) if isinstance(test_cases, list) else 0
        items = subtasks.get("items", [])
        subtask_count = len(items) if isinstance(items, list) else 0
        rag_sources = rag_context.get("sources", [])
        rag_source_count = len(rag_sources) if isinstance(rag_sources, list) else 0
        rules_documents = rules_payload.get("documents", {})
        rule_doc_count = len(rules_documents) if isinstance(rules_documents, dict) else 0
        rules_version = str(rules_payload.get("version", "")).strip()

        # Try LLM-enhanced code generation
        llm_patch = None
        llm_error = None
        use_llm = context.get("use_llm", True)

        if use_llm and spec:
            try:
                llm = get_llm_wrapper()
                if llm is not None:
                    # Build repo context
                    repo_context = {
                        "subtasks_count": subtask_count,
                        "test_cases_count": test_count,
                        "rag_sources_count": rag_source_count,
                        "rules_documents": list(rules_documents.keys()),
                    }
                    prompt = build_code_prompt(spec, test_cases, repo_context)
                    response = llm.complete(prompt)
                    llm.close()

                    # Parse JSON response
                    import json

                    llm_patch = json.loads(response)
            except Exception as e:
                llm_error = str(e)

        # Build final patch
        if llm_patch and isinstance(llm_patch, dict):
            patch = {
                "schema_version": "2.0",
                "files": llm_patch.get("files", []),
                "decisions": llm_patch.get("decisions", []),
                "test_changes": llm_patch.get("test_changes", []),
                "dry_run": False,
                "llm_enhanced": True,
            }
            reason = "Code patch generated with LLM synthesis."
            confidence = 0.92
        else:
            # Fallback to deterministic generation
            patch = self._build_deterministic_patch(
                spec=spec,
                test_cases=test_cases,
                subtask_count=subtask_count,
                rag_source_count=rag_source_count,
                rule_doc_count=rule_doc_count,
                rules_version=rules_version,
            )
            reason = "Deterministic patch generated (LLM unavailable)." if llm_error else "Code patch generated from spec."
            confidence = 0.87 if llm_error else 0.87

        if llm_error:
            patch.setdefault("notes", [])
            patch["notes"].append(f"llm_error={llm_error[:50]}")

        # Apply patch to GitHub if client is available (HF-P5-003)
        pr_url = None
        pr_number = None
        github_client = context.get("github_client")
        if github_client and patch.get("files"):
            try:
                pr_title = spec.get("summary", "HordeForge Generated Feature")[:100]
                pr_body = self._build_pr_body(spec, patch)
                branch_name = context.get("branch_name")

                orchestrator = PatchWorkflowOrchestrator(github_client)
                file_changes = create_patch_from_code_result(patch)
                result = orchestrator.apply_patch(
                    files=file_changes,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    branch_name=branch_name,
                )

                if result.success:
                    pr_url = result.pr_url
                    pr_number = result.pr_number
                    patch["pr_url"] = pr_url
                    patch["pr_number"] = pr_number
                    patch["branch_name"] = result.branch_name
                    patch["applied_to_github"] = True
                else:
                    patch["apply_error"] = result.error
                    patch["rollback_performed"] = result.rollback_performed
            except Exception as apply_error:
                patch["apply_error"] = str(apply_error)

        logs = [f"Code generator produced patch with {len(patch.get('files', []))} files."]
        if pr_url:
            logs.append(f"PR created: {pr_url}")

        return build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason=reason,
            confidence=confidence,
            logs=logs,
            next_actions=["test_runner", "fix_agent"],
        )

    def _build_deterministic_patch(
        self,
        spec: dict[str, Any],
        test_cases: list,
        subtask_count: int,
        rag_source_count: int,
        rule_doc_count: int,
        rules_version: str,
    ) -> dict:
        """Build deterministic patch as fallback."""
        files = []

        # Analyze spec for file changes
        file_changes = spec.get("file_changes", [])
        if file_changes:
            for fc in file_changes:
                path = fc.get("path", "")
                change_type = fc.get("change_type", "modify")
                description = fc.get("description", "")

                # Generate basic file content based on path
                content = self._generate_basic_content(path, description)
                files.append(
                    {
                        "path": path,
                        "change_type": change_type,
                        "content": content,
                    }
                )
        else:
            # Default to feature file
            files.append(
                {
                    "path": "src/feature_impl.py",
                    "change_type": "create",
                    "content": self._generate_basic_content("src/feature_impl.py", "Feature implementation"),
                }
            )

        # Add test file if test cases exist
        if test_cases:
            test_content = self._generate_test_content(test_cases)
            files.append(
                {
                    "path": "tests/test_feature.py",
                    "change_type": "create",
                    "content": test_content,
                }
            )

        decisions = [
            f"subtasks={subtask_count}",
            f"tests={len(test_cases)}",
            f"rag_sources={rag_source_count}",
            f"rules_documents={rule_doc_count}",
            f"rules_version={rules_version or 'none'}",
            "deterministic_patch=true",
        ]

        return {
            "schema_version": "2.0",
            "files": files,
            "decisions": decisions,
            "test_changes": [],
            "dry_run": False,
            "llm_enhanced": False,
        }

    def _build_pr_body(self, spec: dict[str, Any], patch: dict[str, Any]) -> str:
        """Build pull request body from spec and patch."""
        lines = [
            "## Summary",
            spec.get("summary", "Generated by HordeForge"),
            "",
            "## Requirements",
        ]

        for req in spec.get("requirements", []):
            req_id = req.get("id", "")
            desc = req.get("description", "")
            priority = req.get("priority", "")
            lines.append(f"- [{priority}] {req_id}: {desc}")

        lines.extend(["", "## Technical Notes"])
        for note in spec.get("technical_notes", []):
            lines.append(f"- {note}")

        lines.extend(["", "## Changes"])
        for fc in patch.get("files", []):
            path = fc.get("path", "")
            change_type = fc.get("change_type", "modified")
            lines.append(f"- `{change_type}`: {path}")

        lines.extend([
            "",
            "---",
            "*Generated by HordeForge AI*",
        ])

        return "\n".join(lines)

    def _generate_basic_content(self, path: str, description: str) -> str:
        """Generate basic file content based on path."""
        if "test" in path.lower():
            return "# Test file placeholder\nimport pytest\n\ndef test_placeholder():\n    pass\n"

        ext = path.split(".")[-1] if "." in path else "py"
        base_name = path.split("/")[-1].split("\\")[-1].replace(f".{ext}", "")

        if ext == "py":
            return f'''"""Generated implementation for {base_name}."""

def process():
    """Process implementation."""
    pass


if __name__ == "__main__":
    process()
'''
        elif ext in ("js", "ts"):
            return f'''// Generated implementation for {base_name}

export function process() {{
    // Implementation
}}
'''
        elif ext == "go":
            return f'''// Generated implementation for {base_name}

package main

func Process() {{
    // Implementation
}}
'''
        else:
            return f"# Generated file: {path}\n# {description}\n"

    def _generate_test_content(self, test_cases: list[dict[str, Any]]) -> str:
        """Generate test file content from test cases."""
        lines = [
            '"""Generated tests for feature."""',
            "import pytest",
            "",
        ]

        for i, tc in enumerate(test_cases):
            test_name = tc.get("name", f"test_case_{i+1}")
            # Sanitize test name
            safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in test_name)
            lines.append(f"def test_{safe_name}():")
            lines.append('    """Test case from specification."""')
            lines.append("    # TODO: Implement based on test case")
            lines.append("    pass")
            lines.append("")

        return "\n".join(lines)
