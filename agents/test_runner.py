from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class TestRunner:
    name = "test_runner"
    description = "Simulates test execution and returns structured test_results."

    def _resolve_failure_budget(self, context: dict[str, Any]) -> int:
        fix_patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer"],
            )
            or {}
        )
        if isinstance(fix_patch.get("remaining_failures"), int):
            return max(0, int(fix_patch["remaining_failures"]))

        generated_patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["code_generator"],
            )
            or {}
        )
        if isinstance(generated_patch.get("expected_failures"), int):
            return max(0, int(generated_patch["expected_failures"]))
        return 0

    def run(self, context: dict[str, Any]) -> dict:
        failed = self._resolve_failure_budget(context)
        total = max(1, failed + 3)
        passed = total - failed
        test_results = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "mode": "mock",
        }
        status = "SUCCESS" if failed == 0 else "PARTIAL_SUCCESS"

        result = build_agent_result(
            status=status,
            artifact_type="test_results",
            artifact_content=test_results,
            reason="Test execution simulated in deterministic mock mode.",
            confidence=0.93,
            logs=[f"Simulated tests: total={total}, failed={failed}."],
            next_actions=["fix_agent"] if failed > 0 else ["review_agent"],
        )
        # Loop conditions use top-level path `test_runner.test_results.failed`.
        result["test_results"] = test_results
        return result
