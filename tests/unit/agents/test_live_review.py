"""Unit tests for live GitHub review (HF-P5-006)."""

from unittest.mock import MagicMock

import pytest

from agents.live_review import (
    LiveReviewer,
    ReviewComment,
    ReviewResult,
    create_review_from_analysis,
)


class TestReviewComment:
    """Tests for ReviewComment dataclass."""

    def test_default_values(self):
        """Test default ReviewComment values."""
        comment = ReviewComment(path="test.py", line=10, body="Fix this")

        assert comment.path == "test.py"
        assert comment.line == 10
        assert comment.body == "Fix this"
        assert comment.severity == "COMMENT"

    def test_with_severity(self):
        """Test ReviewComment with severity."""
        comment = ReviewComment(
            path="test.py",
            line=10,
            body="Critical issue",
            severity="ERROR",
        )
        assert comment.severity == "ERROR"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_success_result(self):
        """Test successful ReviewResult."""
        result = ReviewResult(success=True, review_id=123, state="APPROVED")

        assert result.success is True
        assert result.review_id == 123
        assert result.state == "APPROVED"
        assert result.error is None

    def test_failure_result(self):
        """Test failed ReviewResult."""
        result = ReviewResult(success=False, error="API error")

        assert result.success is False
        assert result.error == "API error"


class TestLiveReviewer:
    """Tests for LiveReviewer class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        client = MagicMock()
        client.submit_review = MagicMock(return_value={"id": 123, "state": "COMMENTED"})
        client.create_review_comment = MagicMock(return_value={"id": 456})
        client.get_pull_request = MagicMock(return_value={"head": {"sha": "abc123"}})
        return client

    @pytest.fixture
    def reviewer(self, mock_client):
        """Create LiveReviewer with mock client."""
        return LiveReviewer(mock_client)

    def test_submit_review_success(self, reviewer, mock_client):
        """Test successful review submission."""
        comments = [ReviewComment(path="test.py", line=10, body="Good job")]

        result = reviewer.submit_review(
            pull_number=1,
            comments=comments,
            body="Great work!",
            event="APPROVE",
        )

        assert result.success is True
        assert result.review_id == 123
        assert result.state == "COMMENTED"
        mock_client.submit_review.assert_called_once()

    def test_submit_review_failure(self, reviewer, mock_client):
        """Test failed review submission."""
        mock_client.submit_review.side_effect = Exception("API Error")

        comments = [ReviewComment(path="test.py", line=10, body="Fix this")]

        result = reviewer.submit_review(pull_number=1, comments=comments)

        assert result.success is False
        assert result.error == "API Error"

    def test_create_inline_comments(self, reviewer, mock_client):
        """Test creating inline comments."""
        comments = [
            ReviewComment(path="src/main.py", line=5, body="Style issue"),
            ReviewComment(path="src/main.py", line=10, body="Logic issue"),
        ]

        result = reviewer.create_inline_comments(pull_number=1, comments=comments)

        assert result.success is True
        assert mock_client.create_review_comment.call_count == 2

    def test_generate_review_summary_no_issues(self, reviewer):
        """Test review summary generation with no issues."""
        code_quality = {"complexity": "low", "maintainability": "good"}
        test_coverage = {"percentage": 85}
        issues = []

        summary, body, comments = reviewer.generate_review_summary(
            code_quality=code_quality,
            test_coverage=test_coverage,
            issues=issues,
        )

        assert "Code Quality" in summary
        assert "Test Coverage" in summary
        assert "85%" in summary
        assert len(comments) == 0

    def test_generate_review_summary_with_issues(self, reviewer):
        """Test review summary generation with issues."""
        code_quality = {"complexity": "high"}
        test_coverage = {"percentage": 85}
        issues = [
            {
                "type": "error",
                "message": "Memory leak detected",
                "path": "src/main.py",
                "line": 50,
            }
        ]

        summary, body, comments = reviewer.generate_review_summary(
            code_quality=code_quality,
            test_coverage=test_coverage,
            issues=issues,
        )

        assert "Memory leak detected" in summary
        assert len(comments) == 1
        assert comments[0].path == "src/main.py"
        assert comments[0].line == 50


class TestCreateReviewFromAnalysis:
    """Tests for create_review_from_analysis function."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        client = MagicMock()
        client.submit_review = MagicMock(return_value={"id": 123, "state": "APPROVED"})
        return client

    def test_auto_approve_clean_pr(self, mock_client):
        """Test auto-approve for clean PR."""
        result = create_review_from_analysis(
            github_client=mock_client,
            pull_number=1,
            code_quality={"score": "good"},
            test_coverage={"percentage": 90},
            issues=[],
            auto_approve=True,
        )

        assert result.success is True
        call_args = mock_client.submit_review.call_args
        assert call_args.kwargs["event"] == "APPROVE"

    def test_request_changes_on_errors(self, mock_client):
        """Test REQUEST_CHANGES when errors present."""
        result = create_review_from_analysis(
            github_client=mock_client,
            pull_number=1,
            code_quality={},
            test_coverage={"percentage": 90},
            issues=[{"type": "error", "message": "Bug", "severity": "error"}],
            auto_approve=True,
        )

        assert result.success is True
        call_args = mock_client.submit_review.call_args
        assert call_args.kwargs["event"] == "REQUEST_CHANGES"

    def test_comment_only_no_auto_approve(self, mock_client):
        """Test COMMENT event when not auto-approving."""
        result = create_review_from_analysis(
            github_client=mock_client,
            pull_number=1,
            code_quality={},
            test_coverage={"percentage": 90},
            issues=[],
            auto_approve=False,
        )

        assert result.success is True
        call_args = mock_client.submit_review.call_args
        assert call_args.kwargs["event"] == "COMMENT"
