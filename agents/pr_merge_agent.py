from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class PrMergeAgent:
    name = "pr_merge_agent"
    description = "Produces merge decision with optional live GitHub merge."

    def run(self, context: dict[str, Any]) -> dict:
        # Get GitHub client if available (HF-P5-007)
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

        # Live GitHub merge (HF-P5-007)
        merged = False
        live_merge = False
        merge_error = None

        if github_client and pr_number and approved:
            live_merge = True
            try:
                # Check merge conditions
                mergeable = self._check_merge_conditions(github_client, pr_number)
                if mergeable:
                    result = github_client.merge_pull_request(pr_number, merge_method="squash")
                    merged = result.get("merged", False)
                else:
                    merge_error = "PR not mergeable (conflicts or checks failing)"
            except Exception as e:
                merge_error = str(e)
        elif approved:
            # Dry-run mode: simulate successful merge when approved
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
            reason=f"Live merge: {merge_error}" if merge_error else ("Merge decision generated from review_result." if not live_merge else "Merge completed successfully."),
            confidence=0.9 if merged or approved else 0.7,
            logs=[f"Merge decision: merged={merged}, live={live_merge}."],
            next_actions=["ci_monitor_agent"] if merged else ["request_human_review"],
        )

    def _check_merge_conditions(self, github_client: Any, pr_number: int) -> bool:
        """Check if PR meets merge conditions."""
        try:
            # Check mergeable status
            status = github_client.get_mergeable_status(pr_number)
            if not status.get("mergeable", True):
                return False

            # Check if PR is a draft
            if status.get("draft", False):
                return False

            # Check CI status
            pr = github_client.get_pull_request(pr_number)
            head_sha = pr.get("head", {}).get("sha")
            if head_sha:
                combined = github_client.get_combined_status(head_sha)
                state = combined.get("state", "unknown")
                if state != "success":
                    # Allow pending but not failed
                    if state == "failure":
                        return False

            return True
        except Exception:
            return False
