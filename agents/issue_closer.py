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

    def run(self, context: dict[str, Any]) -> dict:
        # Extract DoD information from context - check direct key first, then use get_artifact_from_context
        dod_info = (
            context.get("dod")
            or get_artifact_from_context(
                context,
                "dod",
                preferred_steps=["dod_extractor", "planner"],
            )
            or {}
        )

        # Extract CI status from context - check direct key first, then use get_artifact_from_context
        ci_status = (
            context.get("ci_status")
            or get_artifact_from_context(
                context,
                "ci_status",
                preferred_steps=["ci_verification", "ci_monitoring"],
            )
            or "unknown"
        )

        # Get issue ID from context
        issue_id = context.get("issue_id", context.get("current_issue_id", 0))

        # Perform DoD verification
        dod_result = verify_dod(dod_info)

        # Perform CI verification
        ci_result = verify_ci(ci_status)

        # Attempt to close issue based on verification results
        close_result = close_issue(issue_id, dod_result, ci_result)

        # Determine agent status based on close result
        agent_status = "SUCCESS" if close_result["status"] == "closed" else "PARTIAL_SUCCESS"

        # Prepare result
        result = {
            "issue_id": close_result["issue_id"],
            "final_status": close_result["status"],
            "dod_result": dod_result,
            "ci_result": ci_result,
            "close_reason": close_result["reason"],
        }

        return build_agent_result(
            status=agent_status,
            artifact_type="issue_closure_result",
            artifact_content=result,
            reason=f"Issue closure decision: {close_result['reason']}",
            confidence=0.95 if close_result["status"] == "closed" else 0.75,
            logs=[
                f"DoD verification: {dod_result}",
                f"CI verification: {ci_result}",
                f"Issue {issue_id} status: {close_result['status']} ({close_result['reason']})",
            ],
            next_actions=[]
            if close_result["status"] == "closed"
            else ["keep_open", "investigate_issues"],
        )
