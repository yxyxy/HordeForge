from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import (
    build_agent_result,
    get_artifact_from_context,
    get_artifact_from_result,
)

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
        code_patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["code_generator", "fix_agent"],
            )
            or {}
        )
        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["test_runner"],
            )
            or {}
        )

        if not isinstance(pr_number, int):
            pr_from_patch = code_patch.get("pr_number") if isinstance(code_patch, dict) else None
            if isinstance(pr_from_patch, int):
                pr_number = pr_from_patch
            else:
                # Use step-scoped retrieval to avoid top-level `code_patch` alias
                # overriding code_generator output with fix_agent patch content.
                codegen_step_result = context.get("code_generator")
                codegen_patch = (
                    get_artifact_from_result(codegen_step_result, "code_patch")
                    if isinstance(codegen_step_result, dict)
                    else None
                ) or {}
                pr_from_codegen = (
                    codegen_patch.get("pr_number") if isinstance(codegen_patch, dict) else None
                )
                if isinstance(pr_from_codegen, int):
                    pr_number = pr_from_codegen

        decision = review.get("decision")
        approved = decision == "approve"
        tests_passed = self._tests_passed(test_results)
        has_pr = isinstance(pr_number, int) and pr_number > 0

        gate_fail_reasons: list[str] = []
        if not approved:
            gate_fail_reasons.append("review_not_approved")
        if not tests_passed:
            gate_fail_reasons.append("tests_not_passed")
        if not has_pr:
            gate_fail_reasons.append("pr_missing")

        merged = False
        live_merge = False
        merge_error = None

        if not gate_fail_reasons and github_client and has_pr:
            live_merge = True
            try:
                mergeable = self._check_merge_conditions(github_client, int(pr_number))

                if mergeable:
                    result = github_client.merge_pull_request(int(pr_number), merge_method="squash")
                    merged = result.get("merged", False)
                else:
                    merge_error = "PR not mergeable (conflicts or checks failing)"

            except Exception as e:
                merge_error = str(e)

        merge_status = {
            "dry_run": not live_merge,
            "merged": merged,
            "strategy": "squash",
            "reason": merge_error
            or (
                "approved_by_review_and_tests"
                if not gate_fail_reasons and not live_merge
                else ",".join(gate_fail_reasons)
                if gate_fail_reasons
                else "approved_by_review_and_tests"
            ),
            "live_merge": live_merge,
            "merge_error": merge_error,
            "review_approved": approved,
            "tests_passed": tests_passed,
            "pr_number": pr_number if has_pr else None,
        }

        status = "SUCCESS" if merged else "PARTIAL_SUCCESS"
        reason = (
            f"Live merge failed: {merge_error}"
            if merge_error
            else "Merge completed successfully."
            if merged
            else "Merge blocked by safety gates."
            if gate_fail_reasons
            else "Dry-run merge decision generated."
        )

        return build_agent_result(
            status=status,
            artifact_type="merge_status",
            artifact_content=merge_status,
            reason=reason,
            confidence=0.9 if merged else 0.75 if not gate_fail_reasons else 0.7,
            logs=[
                f"Merge decision: merged={merged}, live={live_merge}.",
                f"Gate review_approved={approved}, tests_passed={tests_passed}, has_pr={has_pr}.",
            ],
            next_actions=["ci_monitor_agent"] if merged else ["request_human_review"],
        )

    @staticmethod
    def _tests_passed(test_results: dict[str, Any]) -> bool:
        if not isinstance(test_results, dict):
            return False
        exit_code = test_results.get("exit_code")
        if isinstance(exit_code, int):
            return exit_code == 0
        failed = test_results.get("failed")
        if isinstance(failed, int):
            return failed == 0
        return False

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
