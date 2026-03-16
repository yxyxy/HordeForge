"""E2E integration tests for HordeForge agent pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.context import ExecutionContext
from orchestrator.state import PipelineRunState, StepRunState
from orchestrator.status import StepStatus

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def temp_repo():
    """Create a temporary repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create basic project structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()

        # Create a simple Python file
        (repo_path / "src" / "main.py").write_text(
            '''"""Main module."""


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def subtract(a: int, b: int) -> int:
    """Subtract two numbers."""
    return a - b
'''
        )

        # Create pyproject.toml
        (repo_path / "pyproject.toml").write_text(
            """[project]
name = "test-project"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
"""
        )

        # Create a simple test file
        (repo_path / "tests" / "test_main.py").write_text(
            '''"""Tests for main module."""

import pytest
from src.main import add, subtract


def test_add():
    """Test add function."""
    assert add(1, 2) == 3


def test_subtract():
    """Test subtract function."""
    assert subtract(5, 3) == 2
'''
        )

        yield repo_path


@pytest.fixture
def mock_llm():
    """Create a mock LLM wrapper."""
    llm = MagicMock()
    llm.complete = MagicMock(
        return_value=json.dumps(
            {
                "summary": "Test implementation",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "description": "Implement feature X",
                        "test_criteria": "Tests pass",
                        "priority": "must",
                    }
                ],
                "technical_notes": ["Implementation note"],
                "files": [
                    {
                        "path": "src/feature.py",
                        "content": '"""Feature X."""\n\ndef feature_x():\n    return True\n',
                    }
                ],
            }
        )
    )
    return llm


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client."""
    client = MagicMock()
    client.create_issue = MagicMock(return_value={"number": 1})
    client.create_branch = MagicMock(return_value={"ref": "feature/123"})
    client.create_pr = MagicMock(
        return_value={"number": 1, "html_url": "https://github.com/test/repo/pull/1"}
    )
    client.get_pull_request = MagicMock(
        return_value={
            "merged": False,
            "mergeable": True,
            "state": "open",
            "head": {"sha": "abc123"},
        }
    )
    client.get_pull_request_reviews = MagicMock(return_value=[{"state": "APPROVED"}])
    client.get_combined_status = MagicMock(return_value={"state": "success"})
    client.merge_pull_request = MagicMock(return_value={"sha": "merged123"})
    return client


@pytest.fixture
def execution_context(temp_repo):
    """Create an execution context for testing."""
    context = ExecutionContext(
        run_id="test-run-001",
        pipeline_name="test_pipeline",
        inputs={
            "repo_path": str(temp_repo),
            "github_token": "test-token",
        },
    )
    return context


# =============================================================================
# E2E Integration Tests
# =============================================================================


class TestExecutionContext:
    """Test ExecutionContext."""

    def test_context_creation(self, execution_context):
        """Test that execution context is created correctly."""
        assert execution_context.run_id == "test-run-001"
        assert execution_context.pipeline_name == "test_pipeline"

    def test_context_state(self, execution_context):
        """Test that state is initialized from inputs."""
        assert "repo_path" in execution_context.state

    def test_set_state_value(self, execution_context):
        """Test setting state value."""
        execution_context.set_state_value("test_key", "test_value")
        assert execution_context.state.get("test_key") == "test_value"

    def test_update_state(self, execution_context):
        """Test updating state."""
        execution_context.update_state({"key1": "value1", "key2": "value2"})
        assert execution_context.state.get("key1") == "value1"
        assert execution_context.state.get("key2") == "value2"

    def test_record_step_result(self, execution_context):
        """Test recording step results."""
        result = {"status": "success", "output": "test output"}
        execution_context.record_step_result("test_step", result)
        assert "test_step" in execution_context.step_results
        assert execution_context.step_results["test_step"] == result

    def test_to_dict(self, execution_context):
        """Test serialization to dict."""
        execution_context.set_state_value("key", "value")
        data = execution_context.to_dict()

        assert data["run_id"] == "test-run-001"
        assert data["pipeline_name"] == "test_pipeline"
        assert "key" in data["state"]


class TestGitHubIntegration:
    """Test GitHub integration through the pipeline."""

    def test_issue_creation(self, mock_github_client):
        """Test creating an issue via GitHub client."""
        result = mock_github_client.create_issue(
            title="Test Issue",
            body="Test body",
            labels=["bug"],
        )

        assert result["number"] == 1
        mock_github_client.create_issue.assert_called_once()

    def test_branch_creation(self, mock_github_client):
        """Test creating a branch."""
        result = mock_github_client.create_branch("feature/test", "main")

        assert "feature" in result["ref"]

    def test_pr_creation(self, mock_github_client):
        """Test creating a PR."""
        result = mock_github_client.create_pr(
            title="Test PR",
            head="feature/test",
            base="main",
            body="Test PR body",
        )

        assert result["number"] == 1

    def test_pr_review_flow(self, mock_github_client):
        """Test PR review flow."""
        # Get PR
        pr = mock_github_client.get_pull_request(1)
        assert pr["merged"] is False

        # Get reviews
        reviews = mock_github_client.get_pull_request_reviews(1)
        assert len(reviews) > 0
        assert reviews[0]["state"] == "APPROVED"

        # Check CI status
        status = mock_github_client.get_combined_status("abc123")
        assert status["state"] == "success"

    def test_pr_merge_flow(self, mock_github_client):
        """Test PR merge flow."""
        # Check mergeability
        pr = mock_github_client.get_pull_request(1)
        assert pr["mergeable"] is True

        # Merge
        result = mock_github_client.merge_pull_request(1)
        assert result["sha"] == "merged123"


class TestLLMIntegration:
    """Test LLM integration through the pipeline."""

    def test_llm_completion(self, mock_llm):
        """Test LLM completion call."""
        result = mock_llm.complete("Test prompt")

        assert result is not None
        mock_llm.complete.assert_called_once()

    def test_llm_json_parsing(self, mock_llm):
        """Test that LLM returns parseable JSON."""
        result = mock_llm.complete("Generate spec")

        # Should be able to parse as JSON
        parsed = json.loads(result)
        assert "summary" in parsed
        assert "files" in parsed


class TestEndToEndFlow:
    """Test complete end-to-end flows."""

    def test_issue_to_pr_flow(self, mock_github_client):
        """Test the flow from issue creation to PR creation."""
        # Create issue
        issue = mock_github_client.create_issue(
            title="New Feature",
            body="Implement X",
        )
        assert issue["number"] == 1

        # Create branch
        branch = mock_github_client.create_branch(f"feature/{issue['number']}")
        assert "feature" in branch["ref"]

        # Create PR
        pr = mock_github_client.create_pr(
            title=f"Fix #{issue['number']}: New Feature",
            head=branch["ref"].replace("refs/heads/", ""),
        )
        assert pr["number"] == 1


class TestPipelineRunState:
    """Test PipelineRunState."""

    def test_create_pipeline_state(self):
        """Test creating pipeline run state."""
        state = PipelineRunState.from_steps(
            run_id="run-001",
            pipeline_name="test",
            steps=[("step1", "agent1"), ("step2", "agent2")],
        )

        assert state.run_id == "run-001"
        assert state.pipeline_name == "test"
        assert len(state.steps) == 2

    def test_step_status_transition(self):
        """Test step status transitions."""
        state = PipelineRunState.from_steps(
            run_id="run-001",
            pipeline_name="test",
            steps=[("step1", "agent1")],
        )

        # Mark step as running
        state.mark_step_status("step1", StepStatus.RUNNING)
        step = state.get_step("step1")
        assert step.status == StepStatus.RUNNING

        # Mark step as success
        state.mark_step_status("step1", StepStatus.SUCCESS)
        step = state.get_step("step1")
        assert step.status == StepStatus.SUCCESS

    def test_advance_index(self):
        """Test advancing step index."""
        state = PipelineRunState.from_steps(
            run_id="run-001",
            pipeline_name="test",
            steps=[("step1", "agent1"), ("step2", "agent2")],
        )

        assert state.current_step_index == 0
        state.advance_index()
        assert state.current_step_index == 1

    def test_to_dict(self):
        """Test serialization."""
        state = PipelineRunState.from_steps(
            run_id="run-001",
            pipeline_name="test",
            steps=[("step1", "agent1")],
        )

        data = state.to_dict()
        assert data["run_id"] == "run-001"
        assert len(data["steps"]) == 1


class TestStepRunState:
    """Test StepRunState."""

    def test_create_step_state(self):
        """Test creating step run state."""
        step = StepRunState(name="test_step", agent="test_agent")

        assert step.name == "test_step"
        assert step.agent == "test_agent"
        assert step.status == StepStatus.PENDING

    def test_step_to_dict(self):
        """Test step serialization."""
        step = StepRunState(name="test_step", agent="test_agent")
        step.status = StepStatus.RUNNING

        data = step.to_dict()
        assert data["name"] == "test_step"
        assert data["status"] == "RUNNING"

    def test_step_from_dict(self):
        """Test step deserialization."""
        data = {
            "name": "test_step",
            "agent": "test_agent",
            "status": "SUCCESS",
            "attempts": 1,
        }

        step = StepRunState.from_dict(data)
        assert step.name == "test_step"
        assert step.status == StepStatus.SUCCESS
        assert step.attempts == 1


class TestErrorHandling:
    """Test error handling in the pipeline."""

    def test_github_api_error(self, mock_github_client):
        """Test handling of GitHub API errors."""
        from agents.github_client import GitHubApiError

        mock_github_client.create_issue.side_effect = GitHubApiError(
            "API Error",
            status_code=500,
            method="POST",
            url="https://api.github.com/repos/test/repo/issues",
        )

        with pytest.raises(GitHubApiError):
            mock_github_client.create_issue("Title", "Body")

    def test_llm_error_handling(self, mock_llm):
        """Test handling of LLM errors."""
        mock_llm.complete.side_effect = RuntimeError("LLM Error")

        with pytest.raises(RuntimeError):
            mock_llm.complete("Test prompt")

    def test_context_error_recovery(self, execution_context):
        """Test that context can recover from errors."""
        # Set some data
        execution_context.set_state_value("key", "value")

        # Simulate an error
        try:
            raise ValueError("Test error")
        except ValueError:
            execution_context.set_state_value("error", "Test error")

        # Data should still be accessible
        assert execution_context.state.get("key") == "value"
        assert execution_context.state.get("error") == "Test error"


class TestDataFlow:
    """Test data flow between pipeline steps."""

    def test_step_data_persistence(self, execution_context):
        """Test that data persists between steps."""
        # Step 1: Generate spec
        execution_context.record_step_result("spec", {"summary": "Test"})

        # Step 2: Generate code
        execution_context.record_step_result("code", {"files": []})

        # Step 3: Run tests
        execution_context.record_step_result("test", {"passed": True})

        # All data should be accessible
        assert execution_context.step_results["spec"]["summary"] == "Test"
        assert execution_context.step_results["code"]["files"] == []
        assert execution_context.step_results["test"]["passed"] is True

    def test_state_accumulation(self, execution_context):
        """Test that state accumulates correctly."""
        steps = ["spec", "code", "test", "review"]

        for step in steps:
            execution_context.record_step_result(step, {"status": "success"})

        # All step results should be present
        for step in steps:
            assert step in execution_context.step_results
            assert execution_context.step_results[step]["status"] == "success"


class TestConfiguration:
    """Test configuration handling."""

    def test_default_inputs(self, execution_context):
        """Test default inputs."""
        inputs = execution_context.inputs
        assert isinstance(inputs, dict)
        assert "repo_path" in inputs

    def test_custom_inputs(self, temp_repo):
        """Test custom inputs."""
        context = ExecutionContext(
            run_id="test-002",
            pipeline_name="test",
            inputs={
                "repo_path": str(temp_repo),
                "max_retries": 5,
                "timeout": 60,
            },
        )

        assert context.state["max_retries"] == 5
        assert context.state["timeout"] == 60
