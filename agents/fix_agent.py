from __future__ import annotations

import re
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import build_code_prompt, get_llm_wrapper
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_prompt,
)


class FixAgent(BaseAgent):
    name = "fix_agent"
    description = "Produces iterative fixes based on failing test results."

    @staticmethod
    def parse_stacktrace(stacktrace: str) -> dict[str, Any] | None:
        """
        Parse stacktrace to extract file and line number.

        Args:
            stacktrace: Stacktrace string

        Returns:
            Dict with file and line or None if parsing fails
        """
        if not stacktrace:
            return None

        # Python stacktrace pattern
        python_pattern = r"File\s+['\"]([^'\"]+)['\"]\s*,\s*line\s*(\d+)"
        python_match = re.search(python_pattern, stacktrace)

        if python_match:
            return {
                "file": python_match.group(1),
                "line": int(python_match.group(2)),
                "language": "python",
            }

        # JavaScript stacktrace pattern
        js_pattern = r"at\s+([^\s:]+):(\d+):(\d+)"
        js_match = re.search(js_pattern, stacktrace)

        if js_match:
            return {
                "file": js_match.group(1),
                "line": int(js_match.group(2)),
                "language": "javascript",
            }

        return None

    @staticmethod
    def detect_failure(output: str) -> dict[str, Any] | None:
        """
        Detect failure type from test output.

        Args:
            output: Test output string

        Returns:
            Dict with failure type and message or None if no failure detected
        """
        if not output:
            return None

        output_lower = output.lower()

        # Pytest assertion
        if "assertionerror" in output_lower:
            return {"type": "assertion", "message": output}

        # Jest assertion
        if "expected:" in output_lower and "received:" in output_lower:
            return {"type": "assertion", "message": output}

        # Exceptions
        if "attributeerror" in output_lower:
            return {"type": "exception", "message": output}

        if "indexerror" in output_lower:
            return {"type": "exception", "message": output}

        if "keyerror" in output_lower:
            return {"type": "exception", "message": output}

        if "zerodivisionerror" in output_lower:
            return {"type": "exception", "message": output}

        # Syntax error
        if "syntaxerror" in output_lower:
            return {"type": "syntax_error", "message": output}

        # Unknown error
        return {"type": "unknown", "message": output}

    @staticmethod
    def generate_fix(failure: dict[str, Any]) -> str | None:
        """
        Generate code fix based on failure type.

        Args:
            failure: Dict with failure type and message

        Returns:
            Fix suggestion string or None
        """
        failure_type = failure.get("type", "")
        message = failure.get("message", "").lower()

        if failure_type == "assertion":
            if "expected" in message and "got" in message:
                # Off-by-one error
                if "expected 3 got 2" in message or "expected 2 got 1" in message:
                    return "Increment the value by 1 to fix off-by-one error."
                # Value mismatch
                else:
                    return "Check the expected value and adjust the code accordingly."

        elif failure_type == "exception":
            if "nonetype" in message or "'noneType'" in message:
                return "Add null/None check before accessing the object."
            elif "indexerror" in message:
                return "Check array/list bounds before accessing by index."
            elif "keyerror" in message:
                return "Check if key exists in dictionary before accessing."
            elif "zerodivisionerror" in message:
                return "Add check for zero before division operation."

        elif failure_type == "syntax_error":
            return "Fix syntax error in the code."

        # Generic fix for unknown errors
        return "Review the error message and implement appropriate fix."

    @staticmethod
    def _extract_failed_tests(context: dict[str, Any]) -> int:
        test_runner_result = context.get("test_runner")
        if isinstance(test_runner_result, dict):
            payload = test_runner_result.get("test_results")
            if isinstance(payload, dict) and isinstance(payload.get("failed"), int):
                return max(0, int(payload["failed"]))

        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["test_runner"],
            )
            or {}
        )
        if isinstance(test_results.get("failed"), int):
            return max(0, int(test_results["failed"]))
        return 0

    def _resolve_iteration(self, context: dict[str, Any]) -> int:
        # First try to get through standard mechanism
        previous_fix = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer"],
            )
            or {}
        )

        # If not found through standard mechanism, check direct path
        if not previous_fix and "fix_agent" in context and "code_patch" in context["fix_agent"]:
            previous_fix = context["fix_agent"]["code_patch"]

        fix_iteration = previous_fix.get("fix_iteration")
        if isinstance(fix_iteration, int):
            return fix_iteration + 1
        elif fix_iteration is not None:
            # Handle case where fix_iteration might be a numeric string or other type
            try:
                return int(fix_iteration) + 1
            except (ValueError, TypeError):
                pass
        return 1

    def run(self, context: dict[str, Any]) -> dict:
        failed = self._extract_failed_tests(context)
        iteration = self._resolve_iteration(context)
        remaining_failures = max(0, failed - 1)

        # Try to use LLM for enhanced fix generation
        use_llm = context.get("use_llm", True)
        llm_fix_result = None
        llm_error = None

        if use_llm:
            try:
                # Try to use the new LLM wrapper first, fall back to legacy if needed
                llm = get_llm_wrapper()
                if llm is None:
                    # Try legacy wrapper for backward compatibility
                    llm = get_legacy_llm_wrapper()

                if llm is not None:
                    # Get test results and failure information
                    test_results = (
                        get_artifact_from_context(
                            context,
                            "test_results",
                            preferred_steps=["test_runner"],
                        )
                        or {}
                    )

                    failure_info = test_results.get("failures", [])
                    if not failure_info:
                        # Try to get failure info from context
                        failure_info = context.get("failures", [])

                    if failure_info:
                        # Build prompt for LLM to generate fix
                        # Try new prompt building first, fall back to legacy if needed
                        try:
                            prompt = build_code_prompt(
                                {"summary": f"Fix iteration {iteration}", "requirements": []},
                                failure_info,
                                {"language": "python"},
                            )
                        except AttributeError:
                            # Fall back to legacy prompt building
                            prompt = legacy_build_code_prompt(
                                {"summary": f"Fix iteration {iteration}", "requirements": []},
                                failure_info,
                                {"language": "python"},
                            )

                        response = llm.complete(prompt)
                        llm.close()

                        # Parse response to extract fix
                        import json

                        try:
                            llm_fix_result = json.loads(response)
                        except json.JSONDecodeError:
                            # If response is not JSON, treat as simple fix suggestion
                            llm_fix_result = {
                                "files": [
                                    {
                                        "path": "src/feature_impl.py",
                                        "content": f"# Fix suggestion from LLM:\n{response}",
                                        "change_type": "modify",
                                    }
                                ]
                            }
            except Exception as e:
                llm_error = str(e)

        if llm_fix_result and isinstance(llm_fix_result, dict):
            # Use LLM-generated fix
            files = llm_fix_result.get("files", [])
            decisions = llm_fix_result.get("decisions", [])
            reason = "Fix patch generated with LLM enhancement."
            confidence = 0.92
        else:
            # Fallback to deterministic fix generation
            files = [
                {
                    "path": "src/feature_impl.py",
                    "content": f"# fix iteration {iteration}\n# Failed before: {failed}\n# Remaining after fix: {remaining_failures}\n",
                    "change_type": "modify",
                }
            ]
            decisions = [
                f"failed_before={failed}",
                f"remaining_after_fix={remaining_failures}",
            ]
            reason = (
                "Deterministic fix patch generated (LLM unavailable)."
                if llm_error
                else "Fix patch generated from test failure analysis."
            )
            confidence = 0.85

        patch = {
            "schema_version": "1.0",
            "files": files,
            "decisions": decisions,
            "fix_iteration": iteration,
            "remaining_failures": remaining_failures,
        }

        if llm_error:
            patch.setdefault("notes", [])
            patch["notes"].append(f"llm_error={llm_error[:120]}")

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason=reason,
            confidence=confidence,
            logs=[
                f"Fix iteration {iteration} produced patch.",
                f"Remaining simulated failures: {remaining_failures}.",
            ],
            next_actions=["test_runner"] if remaining_failures > 0 else ["review_agent"],
        )

        # Add artifact_type and artifact_content as direct properties of result
        # for test compatibility
        result["artifact_type"] = "code_patch"
        result["artifact_content"] = patch

        return result
