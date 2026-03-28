"""Unit tests for live GitHub merge (HF-P5-007)."""

from unittest.mock import MagicMock

import pytest

from agents.live_merge import (
    LiveMerger,
    MergeMethod,
    MergeResult,
    auto_merge_on_success,
)


class TestMergeMethod:
    """Tests for MergeMethod enum."""

    def test_merge_values(self):
        """Test merge method values."""
        assert MergeMethod.MERGE.value == "merge"
        assert MergeMethod.SQUASH.value == "squash"
        assert MergeMethod.REBASE.value == "rebase"


class TestMergeResult:
    """Tests for MergeResult dataclass."""

    def test_success_result(self):
        """Test successful MergeResult."""
        result = MergeResult(success=True, merged=True, merge_commit_sha="abc123")

        assert result.success is True
        assert result.merged is True
        assert result.merge_commit_sha == "abc123"
        assert result.error is None

    def test_failure_result(self):
        """Test failed MergeResult."""
        result = MergeResult(success=False, error="Merge conflict")

        assert result.success is False
        assert result.error == "Merge conflict"


class TestLiveMerger:
    """Tests for LiveMerger class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        client = MagicMock()
        client.get_pull_request = MagicMock(
            return_value={
                "merged": False,
                "mergeable": True,
                "state": "open",
                "head": {"sha": "abc123"},
                "title": "Test PR",
            }
        )
        client.get_combined_status = MagicMock(return_value={"state": "success"})
        client.merge_pull_request = MagicMock(return_value={"sha": "merged123"})
        client.get_pull_request_reviews = MagicMock(return_value=[])
        return client

    @pytest.fixture
    def merger(self, mock_client):
        """Create LiveMerger with mock client."""
        return LiveMerger(mock_client)

    def test_can_merge_success(self, merger, mock_client):
        """Test can_merge when PR is ready."""
        can_merge, reason = merger.can_merge(1)

        assert can_merge is True
        assert reason == "Ready to merge"

    def test_can_merge_already_merged(self, merger, mock_client):
        """Test can_merge when already merged."""
        mock_client.get_pull_request.return_value["merged"] = True

        can_merge, reason = merger.can_merge(1)

        assert can_merge is False
        assert "already merged" in reason

    def test_can_merge_conflicts(self, merger, mock_client):
        """Test can_merge with merge conflicts."""
        mock_client.get_pull_request.return_value["mergeable"] = False

        can_merge, reason = merger.can_merge(1)

        assert can_merge is False
        assert "conflicts" in reason

    def test_can_merge_closed(self, merger, mock_client):
        """Test can_merge when PR is closed."""
        mock_client.get_pull_request.return_value["state"] = "closed"

        can_merge, reason = merger.can_merge(1)

        assert can_merge is False
        assert "closed" in reason

    def test_can_merge_ci_not_passed(self, merger, mock_client):
        """Test can_merge when CI is not passing."""
        mock_client.get_combined_status.return_value = {"state": "failed"}

        can_merge, reason = merger.can_merge(1)

        assert can_merge is False
        assert "CI checks" in reason

    def test_merge_success(self, merger, mock_client):
        """Test successful merge."""
        result = merger.merge(pull_number=1, method=MergeMethod.SQUASH)

        assert result.success is True
        assert result.merged is True
        assert result.merge_commit_sha == "merged123"

    def test_merge_failure(self, merger, mock_client):
        """Test failed merge."""
        mock_client.merge_pull_request.side_effect = Exception("Merge failed")

        result = merger.merge(pull_number=1)

        assert result.success is False
        assert result.error == "Merge failed"

    def test_merge_not_ready(self, merger, mock_client):
        """Test merge when not ready."""
        mock_client.get_pull_request.return_value["mergeable"] = False

        result = merger.merge(pull_number=1)

        assert result.success is False
        assert "not mergeable" in result.error.lower()

    def test_merge_if_ready_approved(self, merger, mock_client):
        """Test merge_if_ready with approval."""
        mock_client.get_pull_request_reviews.return_value = [{"state": "APPROVED"}]

        result = merger.merge_if_ready(pull_number=1, require_approval=True)

        assert result.success is True

    def test_merge_if_ready_not_approved(self, merger, mock_client):
        """Test merge_if_ready without approval."""
        mock_client.get_pull_request_reviews.return_value = []

        result = merger.merge_if_ready(pull_number=1, require_approval=True)

        assert result.success is False
        assert "not approved" in result.error

    def test_get_merge_status(self, merger, mock_client):
        """Test get_merge_status."""
        mock_client.get_pull_request_reviews.return_value = [{"state": "APPROVED"}]

        status = merger.get_merge_status(1)

        assert status["pull_request"]["merged"] is False
        assert status["ci_status"] == "success"
        assert status["reviews"]["approved"] is True
        assert status["can_merge"] is True


class TestAutoMergeOnSuccess:
    """Tests for auto_merge_on_success function."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        client = MagicMock()
        client.get_pull_request = MagicMock(
            return_value={
                "merged": False,
                "mergeable": True,
                "state": "open",
                "title": "Test PR",
            }
        )
        client.get_combined_status = MagicMock(return_value={"state": "success"})
        client.merge_pull_request = MagicMock(return_value={"sha": "merged123"})
        client.get_pull_request_reviews = MagicMock(return_value=[{"state": "APPROVED"}])
        return client

    def test_auto_merge_success(self, mock_client):
        """Test successful auto merge."""
        result = auto_merge_on_success(mock_client, pull_number=1)

        assert result.success is True
        assert result.merged is True

    def test_auto_merge_not_ready(self, mock_client):
        """Test auto merge when not ready."""
        mock_client.get_pull_request_reviews.return_value = []

        result = auto_merge_on_success(mock_client, pull_number=1)

        assert result.success is False
        assert "not ready" in result.error.lower()
