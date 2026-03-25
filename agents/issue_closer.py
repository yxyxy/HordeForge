from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context


def verify_dod(dod: dict[str, Any]) -> str:
    """
    Verify Definition of Done checklist

    Args:
        dod: Dictionary containing 'dod' (required items) and 'checked' (completed items)

    Returns:
        "passed" if all required items are checked, "failed" otherwise
    """
    required_items = set(dod.get("dod", []))
    completed_items = set(dod.get("checked", []))

    # Check if all required items are completed
    if required_items.issubset(completed_items):
        return "passed"
    else:
        return "failed"


def verify_ci(status: str) -> str:
    """
    Verify CI status

    Args:
        status: CI status string ("success", "failed", etc.)

    Returns:
        "passed" if CI status is success, "failed" otherwise
    """
    if status.lower() == "success":
        return "passed"
    else:
        return "failed"


def close_issue(issue_id: int, dod_result: str, ci_result: str) -> dict[str, Any]:
    """
    Close issue if both DoD and CI verifications pass

    Args:
        issue_id: ID of the issue to close
        dod_result: Result of DoD verification ("passed" or "failed")
        ci_result: Result of CI verification ("passed" or "failed")

    Returns:
        Dictionary with status and reason
    """
    if dod_result == "passed" and ci_result == "passed":
        return {
            "status": "closed",
            "issue_id": issue_id,
            "reason": "DoD and CI verification passed",
        }
    elif dod_result == "failed":
        return {"status": "open", "issue_id": issue_id, "reason": "DoD verification failed"}
    elif ci_result == "failed":
        return {"status": "open", "issue_id": issue_id, "reason": "CI verification failed"}
    else:
        return {"status": "open", "issue_id": issue_id, "reason": "Unknown verification state"}


class IssueCloser(BaseAgent):
    name = "issue_closer"
    description = "Closes issues after verifying DoD and CI status."

    @staticmethod
    def _extract_failed_count(ci_payload: Any) -> int | None:
        if not isinstance(ci_payload, dict):
            return None

        failed = ci_payload.get("failed")
        if isinstance(failed, int):
            return max(0, failed)

        nested = ci_payload.get("test_results")
        if isinstance(nested, dict) and isinstance(nested.get("failed"), int):
            return max(0, nested["failed"])

        return None

    @staticmethod
    def _ci_passed(ci_payload: Any) -> bool:
        failed_count = IssueCloser._extract_failed_count(ci_payload)
        if failed_count is not None:
            return failed_count == 0

        if isinstance(ci_payload, str):
            return verify_ci(ci_payload) == "passed"

        if isinstance(ci_payload, dict):
            status_value = str(ci_payload.get("status", "")).strip().lower()
            conclusion = str(ci_payload.get("conclusion", "")).strip().lower()
            if status_value in {"success", "passed", "green"}:
                return True
            if conclusion in {"success", "passed"}:
                return True

        return False

    def run(self, context: dict[str, Any]) -> dict:
        dod_info = (
            context.get("dod")
            or get_artifact_from_context(
                context,
                "dod",
                preferred_steps=["dod_extractor", "planner"],
            )
            or {}
        )

        ci_payload = (
            context.get("ci_results")
            or context.get("ci_verification")
            or context.get("ci_status")
            or get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["ci_verification", "test_runner"],
            )
            or {}
        )

        issue = context.get("issue")
        if isinstance(issue, dict) and isinstance(issue.get("id"), int):
            issue_id = issue["id"]
        else:
            issue_id = context.get("issue_id", context.get("current_issue_id", 0))

        dod_result = verify_dod(dod_info)
        ci_result = "passed" if self._ci_passed(ci_payload) else "failed"

        close_issue_flag = dod_result == "passed" and ci_result == "passed"
        if close_issue_flag:
            reason_key = "ready_to_close"
            final_status = "closed"
        elif ci_result != "passed":
            reason_key = "ci_still_failing"
            final_status = "open"
        else:
            reason_key = "dod_not_satisfied"
            final_status = "open"

        result = {
            "issue_id": issue_id,
            "close_issue": close_issue_flag,
            "final_status": final_status,
            "dod_result": dod_result,
            "ci_result": ci_result,
            "reason": reason_key,
            "close_reason": reason_key,
        }

        agent_result = build_agent_result(
            status="SUCCESS" if close_issue_flag else "PARTIAL_SUCCESS",
            artifact_type="close_status",
            artifact_content=result,
            reason=f"Issue closure decision: {reason_key}",
            confidence=0.95 if close_issue_flag else 0.75,
            logs=[
                f"DoD verification: {dod_result}",
                f"CI verification: {ci_result}",
                f"Issue {issue_id} status: {final_status} ({reason_key})",
            ],
            next_actions=[] if close_issue_flag else ["keep_open", "investigate_issues"],
        )

        # Backward compatibility for older tests/consumers.
        agent_result.setdefault("artifacts", [])
        agent_result["artifacts"].append({"type": "issue_closure_result", "content": result})
        return agent_result
