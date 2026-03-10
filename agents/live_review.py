"""Live GitHub review integration - submits PR reviews with generated comments."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.github_client import GitHubClient

logger = logging.getLogger(__name__)


@dataclass
class ReviewComment:
    """Single review comment."""

    path: str
    line: int
    body: str
    severity: str = "COMMENT"  # COMMENT, WARNING, ERROR


@dataclass
class ReviewResult:
    """Result of a review submission."""

    success: bool
    review_id: int | None = None
    state: str | None = None  # APPROVED, CHANGES_REQUESTED, COMMENTED, PENDING
    comments: list[ReviewComment] | None = None
    error: str | None = None


class LiveReviewer:
    """Submits live reviews to GitHub Pull Requests."""

    def __init__(self, github_client: GitHubClient) -> None:
        self.client = github_client

    def submit_review(
        self,
        pull_number: int,
        comments: list[ReviewComment],
        body: str = "",
        event: str = "COMMENT",
    ) -> ReviewResult:
        """Submit a review to a pull request."""
        try:
            formatted_comments = [
                {"path": c.path, "line": c.line, "body": c.body}
                for c in comments
            ]

            response = self.client.submit_review(
                pr_number=pull_number,
                body=body,
                event=event,
                comments=formatted_comments,
            )

            return ReviewResult(
                success=True,
                review_id=response.get("id"),
                state=response.get("state"),
                comments=comments,
            )

        except Exception as e:
            logger.error(f"Failed to submit review: {e}")
            return ReviewResult(success=False, error=str(e), comments=comments)

    def create_inline_comments(
        self,
        pull_number: int,
        comments: list[ReviewComment],
    ) -> ReviewResult:
        """Create inline comments without submitting a full review."""
        results = []
        for comment in comments:
            try:
                self.client.create_review_comment(
                    pr_number=pull_number,
                    body=comment.body,
                    commit_id=self._get_head_commit(pull_number),
                    path=comment.path,
                    line=comment.line,
                )
                results.append(True)
            except Exception as e:
                logger.error(f"Failed to create comment: {e}")
                results.append(False)

        success = all(results)
        return ReviewResult(
            success=success,
            state="COMMENTED" if success else "ERROR",
            comments=comments,
            error=None if success else "Some comments failed",
        )

    def _get_head_commit(self, pull_number: int) -> str:
        """Get the head commit SHA for a pull request."""
        try:
            pr = self.client.get_pull_request(pull_number)
            return pr.get("head", {}).get("sha", "")
        except Exception:
            return ""

    def generate_review_summary(
        self,
        code_quality: dict[str, Any],
        test_coverage: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> tuple[str, str, list[ReviewComment]]:
        """Generate review summary and comments from analysis results."""
        comments = []
        summary_lines = ["## Code Review Summary\n"]

        if code_quality:
            summary_lines.append("### Code Quality")
            for key, value in code_quality.items():
                summary_lines.append(f"- {key}: {value}")

        if test_coverage:
            summary_lines.append("\n### Test Coverage")
            coverage_pct = test_coverage.get("percentage", 0)
            summary_lines.append(f"- Overall: {coverage_pct}%")
            if coverage_pct < 80:
                comments.append(
                    ReviewComment(
                        path="",
                        line=0,
                        body=f"Test coverage is below 80% ({coverage_pct}%). Consider adding more tests.",
                        severity="WARNING",
                    )
                )

        if issues:
            summary_lines.append("\n### Issues Found")
            for issue in issues:
                issue_type = issue.get("type", "issue")
                message = issue.get("message", "")
                path = issue.get("path", "")
                line = issue.get("line", 0)

                summary_lines.append(f"- [{issue_type}] {message}")

                if path:
                    comments.append(
                        ReviewComment(
                            path=path,
                            line=line,
                            body=message,
                            severity="WARNING" if issue_type == "warning" else "ERROR",
                        )
                    )

        summary = "\n".join(summary_lines)
        return summary, summary, comments


def create_review_from_analysis(
    github_client: GitHubClient,
    pull_number: int,
    code_quality: dict[str, Any],
    test_coverage: dict[str, Any],
    issues: list[dict[str, Any]],
    auto_approve: bool = False,
) -> ReviewResult:
    """Convenience function to create a review from analysis results."""
    reviewer = LiveReviewer(github_client)

    _summary, body, comments = reviewer.generate_review_summary(
        code_quality=code_quality,
        test_coverage=test_coverage,
        issues=issues,
    )

    if auto_approve and not issues:
        event = "APPROVE"
    elif any(i.get("severity") == "error" for i in issues):
        event = "REQUEST_CHANGES"
    else:
        event = "COMMENT"

    return reviewer.submit_review(
        pull_number=pull_number,
        comments=comments,
        body=body,
        event=event,
    )
