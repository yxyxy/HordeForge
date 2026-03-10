from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class FixAgent:
    name = "fix_agent"
    description = "Produces iterative fixes based on failing test results."

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
        previous_fix = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer"],
            )
            or {}
        )
        if isinstance(previous_fix.get("fix_iteration"), int):
            return int(previous_fix["fix_iteration"]) + 1
        return 1

    def run(self, context: dict[str, Any]) -> dict:
        failed = self._extract_failed_tests(context)
        iteration = self._resolve_iteration(context)
        remaining_failures = max(0, failed - 1)

        patch = {
            "schema_version": "1.0",
            "files": [
                {
                    "path": "src/feature_impl.py",
                    "diff": f"+# fix iteration {iteration}\n",
                }
            ],
            "decisions": [
                f"failed_before={failed}",
                f"remaining_after_fix={remaining_failures}",
            ],
            "fix_iteration": iteration,
            "remaining_failures": remaining_failures,
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason="Fix patch generated from latest simulated test_results.",
            confidence=0.89,
            logs=[
                f"Fix iteration {iteration} produced patch.",
                f"Remaining simulated failures: {remaining_failures}.",
            ],
            next_actions=["test_runner"] if remaining_failures > 0 else ["review_agent"],
        )
