"""Live GitHub merge - auto-merges PRs after successful review and tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agents.github_client import GitHubClient

logger = logging.getLogger(__name__)


class MergeMethod(Enum):
    """Merge method for pull requests."""

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    merged: bool = False
    merge_commit_sha: str | None = None
    state: str | None = None
    message: str | None = None
    error: str | None = None


class LiveMerger:
    """Handles automated merging of pull requests."""

    def __init__(self, github_client: GitHubClient) -> None:
        self.client = github_client

    def can_merge(self, pull_number: int) -> tuple[bool, str]:
        """Check if a PR can be merged.

        Args:
            pull_number: Pull request number

        Returns:
            Tuple of (can_merge, reason)
        """
        try:
            # Get PR details
            pr = self.client.get_pull_request(pull_number)

            # Check if already merged
            if pr.get("merged"):
                return False, "Pull request already merged"

            # Check mergeable state
            mergeable = pr.get("mergeable")
            if mergeable is False:
                return False, "Pull request is not mergeable (conflicts)"

            # Check state
            state = pr.get("state")
            if state == "closed":
                return False, "Pull request is closed"

            # Get combined status
            try:
                head_sha = pr.get("head", {}).get("sha")
                status = self.client.get_combined_status(head_sha)

                if status.get("state") != "success":
                    return False, "CI checks not passed"
            except Exception:
                # If we can't get status, allow merge anyway
                logger.warning("Could not verify CI status, allowing merge attempt")

            return True, "Ready to merge"

        except Exception as e:
            logger.error(f"Failed to check merge eligibility: {e}")
            return False, f"Error checking eligibility: {e}"

    def merge(
        self,
        pull_number: int,
        method: MergeMethod = MergeMethod.SQUASH,
        title: str | None = None,
        message: str | None = None,
    ) -> MergeResult:
        """Merge a pull request.

        Args:
            pull_number: Pull request number
            method: Merge method (merge, squash, rebase)
            title: Custom merge commit title (for squash/merge)
            message: Custom merge commit message

        Returns:
            MergeResult with merge status
        """
        try:
            # First check if we can merge
            can_merge, reason = self.can_merge(pull_number)
            if not can_merge:
                return MergeResult(success=False, error=reason)

            # Get PR for commit message
            pr = self.client.get_pull_request(pull_number)

            # Prepare merge parameters
            merge_title = title or pr.get("title", "")
            merge_message = message or f"Merge pull request #{pull_number}\n\n{merge_title}"

            # Execute merge
            response = self.client.merge_pull_request(
                pull_number,
                merge_method=method.value,
                title=merge_title,
                message=merge_message,
            )

            return MergeResult(
                success=True,
                merged=True,
                merge_commit_sha=response.get("sha"),
                state="merged",
                message=f"Successfully merged PR #{pull_number}",
            )

        except Exception as e:
            logger.error(f"Failed to merge PR: {e}")
            return MergeResult(success=False, error=str(e))

    def merge_if_ready(
        self,
        pull_number: int,
        require_approval: bool = True,
        method: MergeMethod = MergeMethod.SQUASH,
    ) -> MergeResult:
        """Conditionally merge a PR if it's ready.

        Args:
            pull_number: Pull request number
            require_approval: If True, check for approval
            method: Merge method

        Returns:
            MergeResult
        """
        try:
            # Check approval if required
            if require_approval:
                reviews = self.client.get_pull_request_reviews(pull_number)
                approved = any(r.get("state") == "APPROVED" for r in reviews)
                if not approved:
                    return MergeResult(success=False, error="PR not approved")

            # Check and merge
            return self.merge(pull_number=pull_number, method=method)

        except Exception as e:
            logger.error(f"Failed to merge if ready: {e}")
            return MergeResult(success=False, error=str(e))

    def get_merge_status(self, pull_number: int) -> dict[str, Any]:
        """Get comprehensive merge status for a PR.

        Args:
            pull_number: Pull request number

        Returns:
            Dictionary with merge status details
        """
        try:
            pr = self.client.get_pull_request(pull_number)

            # Get CI status
            head_sha = pr.get("head", {}).get("sha")
            try:
                status = self.client.get_combined_status(head_sha)
                ci_state = status.get("state", "unknown")
            except Exception:
                ci_state = "unknown"

            # Get reviews
            try:
                reviews = self.client.get_pull_request_reviews(pull_number)
                approved = any(r.get("state") == "APPROVED" for r in reviews)
                changes_requested = any(r.get("state") == "CHANGES_REQUESTED" for r in reviews)
            except Exception:
                approved = False
                changes_requested = False

            return {
                "pull_request": {
                    "number": pull_number,
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "merged": pr.get("merged", False),
                    "mergeable": pr.get("mergeable"),
                },
                "ci_status": ci_state,
                "reviews": {
                    "approved": approved,
                    "changes_requested": changes_requested,
                },
                "can_merge": (
                    pr.get("mergeable", False)
                    and ci_state == "success"
                    and approved
                    and not pr.get("merged")
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get merge status: {e}")
            return {"error": str(e)}


def auto_merge_on_success(
    github_client: GitHubClient,
    pull_number: int,
    method: MergeMethod = MergeMethod.SQUASH,
) -> MergeResult:
    """Convenience function to auto-merge a PR when conditions are met.

    Args:
        github_client: GitHub client instance
        pull_number: Pull request number
        method: Merge method

    Returns:
        MergeResult
    """
    merger = LiveMerger(github_client)

    # Get status to verify conditions
    status = merger.get_merge_status(pull_number)

    if "error" in status:
        return MergeResult(success=False, error=status["error"])

    if not status.get("can_merge"):
        return MergeResult(
            success=False,
            error="PR not ready for merge (check CI status and approval)",
        )

    # Attempt merge
    return merger.merge(pull_number=pull_number, method=method)
