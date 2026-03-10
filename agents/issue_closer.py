from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class IssueCloser:
    name = "issue_closer"
    description = "Determines if CI fix issue can be closed based on verification results."

    def _resolve_failed_count(self, context: dict[str, Any]) -> int:
        ci_verification = context.get("ci_verification")
        if isinstance(ci_verification, dict):
            payload = ci_verification.get("test_results")
            if isinstance(payload, dict) and isinstance(payload.get("failed"), int):
                return max(0, int(payload["failed"]))

        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["ci_verification", "test_runner"],
            )
            or {}
        )
        if isinstance(test_results.get("failed"), int):
            return max(0, int(test_results["failed"]))
        return 0

    def run(self, context: dict[str, Any]) -> dict:
        failed = self._resolve_failed_count(context)
        close_issue = failed == 0
        close_status = {
            "close_issue": close_issue,
            "failed_tests": failed,
            "reason": "ci_green" if close_issue else "ci_still_failing",
        }
        return build_agent_result(
            status="SUCCESS" if close_issue else "PARTIAL_SUCCESS",
            artifact_type="close_status",
            artifact_content=close_status,
            reason="Close decision derived from latest CI verification results.",
            confidence=0.92 if close_issue else 0.73,
            logs=[f"Issue close decision: {close_issue} (failed={failed})."],
            next_actions=[] if close_issue else ["create_followup_issue"],
        )
