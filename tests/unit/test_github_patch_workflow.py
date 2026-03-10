"""Unit tests for GitHub patch workflow (HF-P5-003)."""

from unittest.mock import MagicMock

import pytest

from agents.github_client import (
    GitHubApiError,
    GitHubClient,
    GitHubNotFoundError,
)
from agents.patch_workflow import (
    FileChange,
    PatchWorkflowConfig,
    PatchWorkflowOrchestrator,
    PatchWorkflowResult,
    apply_code_patch,
    create_patch_from_code_result,
)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_create_file_change(self):
        """Test creating a FileChange."""
        fc = FileChange(path="test.py", content="print('hello')", change_type="create")
        assert fc.path == "test.py"
        assert fc.content == "print('hello')"
        assert fc.change_type == "create"
        assert fc.sha is None

    def test_file_change_with_sha(self):
        """Test FileChange with SHA for modification."""
        fc = FileChange(
            path="test.py",
            content="print('world')",
            change_type="modify",
            sha="abc123",
        )
        assert fc.sha == "abc123"


class TestPatchWorkflowConfig:
    """Tests for PatchWorkflowConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = PatchWorkflowConfig()
        assert config.branch_prefix == "hordeforge/"
        assert config.base_branch == "main"
        assert config.commit_message_prefix == "HordeForge: "

    def test_custom_config(self):
        """Test custom configuration."""
        config = PatchWorkflowConfig(
            branch_prefix="custom/",
            base_branch="develop",
            commit_message_prefix="Custom: ",
        )
        assert config.branch_prefix == "custom/"
        assert config.base_branch == "develop"
        assert config.commit_message_prefix == "Custom: "


class TestCreatePatchFromCodeResult:
    """Tests for creating patch from code result."""

    def test_basic_code_result(self):
        """Test creating patch from basic code result."""
        code_result = {
            "files": [
                {"path": "main.py", "content": "print('hello')", "change_type": "create"},
                {"path": "utils.py", "content": "def helper(): pass", "change_type": "create"},
            ]
        }
        files = create_patch_from_code_result(code_result)
        assert len(files) == 2
        assert files[0].path == "main.py"
        assert files[1].path == "utils.py"

    def test_empty_files(self):
        """Test with empty files list."""
        files = create_patch_from_code_result({"files": []})
        assert len(files) == 0

    def test_missing_files_key(self):
        """Test with missing files key."""
        files = create_patch_from_code_result({})
        assert len(files) == 0


class TestPatchWorkflowOrchestrator:
    """Tests for PatchWorkflowOrchestrator."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        client = MagicMock(spec=GitHubClient)
        client.get_branch_sha.return_value = "abc123def"
        return client

    @pytest.fixture
    def orchestrator(self, mock_client):
        """Create orchestrator with mock client."""
        return PatchWorkflowOrchestrator(mock_client)

    def test_successful_patch_application(self, mock_client, orchestrator):
        """Test successful patch application."""
        # Mock responses - file doesn't exist so create works
        mock_client.get_file_content.side_effect = GitHubNotFoundError(
            "Not found", method="GET", url="test"
        )
        mock_client.create_branch.return_value = {"ref": "refs/heads/feature-123"}
        mock_client.create_or_update_file.return_value = {"commit": {"sha": "commit123"}}
        mock_client.create_pr.return_value = {"number": 42, "html_url": "https://github.com/test/pr/42"}

        files = [
            FileChange(path="test.py", content="print('hello')", change_type="create"),
        ]

        result = orchestrator.apply_patch(
            files=files,
            pr_title="Add test file",
            pr_body="This PR adds a test file",
        )

        assert result.success is True
        assert result.pr_number == 42
        assert result.pr_url == "https://github.com/test/pr/42"
        assert result.branch_name is not None
        assert result.branch_name.startswith("hordeforge/feature-")
        assert "test.py" in result.files_changed

        # Verify calls
        mock_client.create_branch.assert_called_once()
        mock_client.create_or_update_file.assert_called_once()
        mock_client.create_pr.assert_called_once()

    def test_rollback_on_failure(self, mock_client, orchestrator):
        """Test rollback is performed on failure."""
        # Mock create_branch to succeed, but file operation to fail
        mock_client.get_file_content.side_effect = GitHubNotFoundError(
            "Not found", method="GET", url="test"
        )
        mock_client.create_branch.return_value = {"ref": "refs/heads/feature-123"}
        mock_client.create_or_update_file.side_effect = GitHubApiError(
            "Server error",
            status_code=500,
            method="PUT",
            url="https://api.github.com/contents/test.py",
        )
        mock_client.delete_branch.return_value = {}

        files = [FileChange(path="test.py", content="print('hello')", change_type="create")]

        result = orchestrator.apply_patch(files, "Test PR", "Description")

        assert result.success is False
        assert result.error is not None
        assert result.rollback_performed is True
        mock_client.delete_branch.assert_called_once()

    def test_validation_fails_for_delete_without_sha(self, orchestrator):
        """Test that delete without SHA fails validation."""
        files = [FileChange(path="test.py", content="", change_type="delete")]

        with pytest.raises(ValueError, match="SHA required"):
            orchestrator._validate_patch(files)

    def test_modify_gets_sha_from_existing_file(self, mock_client, orchestrator):
        """Test that modify gets SHA from existing file."""
        mock_client.get_file_content.return_value = {"sha": "existing_sha_123"}

        files = [FileChange(path="test.py", content="new content", change_type="modify")]

        orchestrator._validate_patch(files)

        assert files[0].sha == "existing_sha_123"

    def test_create_when_file_exists_becomes_modify(self, mock_client, orchestrator):
        """Test that create on existing file becomes modify."""
        mock_client.get_file_content.return_value = {"sha": "existing_sha_123"}

        files = [FileChange(path="test.py", content="new content", change_type="create")]

        orchestrator._validate_patch(files)

        assert files[0].change_type == "modify"
        assert files[0].sha == "existing_sha_123"


class TestApplyCodePatch:
    """Tests for convenience function."""

    def test_apply_code_patch_function(self):
        """Test the apply_code_patch convenience function."""
        mock_client = MagicMock(spec=GitHubClient)
        mock_client.get_branch_sha.return_value = "abc123"
        mock_client.get_file_content.side_effect = GitHubNotFoundError(
            "Not found", method="GET", url="test"
        )
        mock_client.create_branch.return_value = {}
        mock_client.create_or_update_file.return_value = {"commit": {"sha": "commit123"}}
        mock_client.create_pr.return_value = {"number": 1, "html_url": "https://github.com/test/pr/1"}

        code_result = {
            "files": [{"path": "test.py", "content": "print('test')", "change_type": "create"}]
        }

        result = apply_code_patch(
            github_client=mock_client,
            code_result=code_result,
            pr_title="Test PR",
            pr_body="Test description",
        )

        assert result.success is True
        assert result.pr_number == 1


class TestPatchWorkflowResult:
    """Tests for PatchWorkflowResult."""

    def test_default_result(self):
        """Test default result values."""
        result = PatchWorkflowResult(success=False)
        assert result.success is False
        assert result.branch_name is None
        assert result.pr_url is None
        assert result.pr_number is None
        assert result.files_changed == []
        assert result.commit_sha is None
        assert result.error is None
        assert result.rollback_performed is False

    def test_successful_result(self):
        """Test result for successful workflow."""
        result = PatchWorkflowResult(
            success=True,
            branch_name="feature-123",
            pr_number=42,
            pr_url="https://github.com/test/pr/42",
            files_changed=["main.py", "utils.py"],
            commit_sha="abc123",
        )
        assert result.success is True
        assert result.pr_number == 42
        assert len(result.files_changed) == 2

    def test_failed_result(self):
        """Test result for failed workflow."""
        result = PatchWorkflowResult(
            success=False,
            branch_name="feature-123",
            error="Something went wrong",
            rollback_performed=True,
        )
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.rollback_performed is True
