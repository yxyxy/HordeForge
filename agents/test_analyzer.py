from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result


class TestAnalyzer:
    name = "test_analyzer"
    description = "Produces deterministic baseline test coverage report."

    @staticmethod
    def _extract_test_files(context: dict[str, Any]) -> list[str]:
        raw = context.get("test_files")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, str)]
        return []

    def run(self, context: dict[str, Any]) -> dict:
        test_files = self._extract_test_files(context)
        total_tests = len(test_files)
        has_tests = total_tests > 0
        status = "SUCCESS" if has_tests else "PARTIAL_SUCCESS"

        report = {
            "total_tests": total_tests,
            "estimated_coverage_percent": 65 if has_tests else 0,
            "test_files": test_files,
            "fallback_reason": "" if has_tests else "No tests discovered in provided context.",
        }
        return build_agent_result(
            status=status,
            artifact_type="test_coverage_report",
            artifact_content=report,
            reason="Coverage report generated via deterministic MVP analyzer.",
            confidence=0.82 if has_tests else 0.68,
            logs=[
                f"Detected {total_tests} test files.",
                "Graceful fallback applied." if not has_tests else "Baseline coverage estimated.",
            ],
            next_actions=["pipeline_initializer"],
        )
