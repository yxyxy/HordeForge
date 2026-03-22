from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context

# =========================
# Queue utilities (TDD)
# =========================


def validate_branch_protection(pr: dict) -> bool:
    """Validate branch protection checks."""
    return pr.get("status") == "success"


def add_to_queue(queue: list, pr: dict) -> list:
    """Add PR to merge queue."""
    queue.append(pr)
    return queue


def process_queue(queue: list):
    """Merge next PR from queue."""
    if not queue:
        return None, queue

    merged = queue.pop(0)
    return merged, queue


def handle_rebase(pr: dict) -> str:
    """Handle rebase requirement."""
    if pr.get("behind"):
        return "rebase"
    return "noop"


# =========================
# Agent
# =========================


class PrMergeAgent(BaseAgent):
    name = "pr_merge_agent"
    description = "Produces merge decision with optional live GitHub merge."

    def run(self, context: dict[str, Any]) -> dict:
        github_client = context.get("github_client")
        pr_number = context.get("pr_number")

        review = (
            get_artifact_from_context(
                context,
                "review_result",
                preferred_steps=["review_agent"],
            )
            or {}
        )

        decision = review.get("decision")
        approved = decision == "approve"

        merged = False
        live_merge = False
        merge_error = None

        if github_client and pr_number and approved:
            live_merge = True
            try:
                mergeable = self._check_merge_conditions(github_client, pr_number)

                if mergeable:
                    result = github_client.merge_pull_request(pr_number, merge_method="squash")
                    merged = result.get("merged", False)
                else:
                    merge_error = "PR not mergeable (conflicts or checks failing)"

            except Exception as e:
                merge_error = str(e)

        elif approved:
            merged = True

        merge_status = {
            "dry_run": not live_merge,
            "merged": merged,
            "strategy": "squash",
            "reason": merge_error or ("approved_by_review" if approved else "review_not_approved"),
            "live_merge": live_merge,
            "merge_error": merge_error,
        }

        return build_agent_result(
            status="SUCCESS" if merged or (approved and not live_merge) else "PARTIAL_SUCCESS",
            artifact_type="merge_status",
            artifact_content=merge_status,
            reason=f"Live merge: {merge_error}"
            if merge_error
            else (
                "Merge decision generated from review_result."
                if not live_merge
                else "Merge completed successfully."
            ),
            confidence=0.9 if merged or approved else 0.7,
            logs=[f"Merge decision: merged={merged}, live={live_merge}."],
            next_actions=["ci_monitor_agent"] if merged else ["request_human_review"],
        )

    def _check_merge_conditions(self, github_client: Any, pr_number: int) -> bool:
        """Check if PR meets merge conditions."""
        try:
            status = github_client.get_mergeable_status(pr_number)

            if not status.get("mergeable", True):
                return False

            if status.get("draft", False):
                return False

            pr = github_client.get_pull_request(pr_number)
            head_sha = pr.get("head", {}).get("sha")

            if head_sha:
                combined = github_client.get_combined_status(head_sha)
                state = combined.get("state", "unknown")

                if state != "success":
                    if state == "failure":
                        return False

            return True

        except Exception:
            return False
