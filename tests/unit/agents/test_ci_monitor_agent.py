"""
Unit tests for CI Monitor Agent
"""

import pytest

from agents.ci_monitor_agent.agent import (
    CIContext,
    CIMonitorAgent,
    detect_failures,
    monitor_ci_status,
    report_status,
)


class TestCIStatusMonitoring:
    """TDD: CI Status Monitoring"""

    def test_monitor_ci_status_success(self):
        """TDD: CI status retrieved successfully"""
        # Arrange
        pipeline_id = "pipeline_123"

        # Act
        result = monitor_ci_status(pipeline_id)

        # Assert
        assert result.status == "success"
        assert result.ci_status == "success"
        assert "ci_status" in result.dict()

    def test_monitor_ci_status_not_found(self):
        """TDD: CI status not found"""
        # Arrange
        pipeline_id = "nonexistent"

        # Act
        result = monitor_ci_status(pipeline_id)

        # Assert
        assert result.status == "not_found"
        assert result.ci_status is None


class TestFailureDetection:
    """TDD: Failure Detection"""

    def test_detect_failures_success(self):
        """TDD: Failure detected"""
        # Arrange
        ci_status = "failed"

        # Act
        result = detect_failures(ci_status)

        # Assert
        assert result.status == "failure_detected"
        assert result.failure_detected is True

    def test_detect_failures_none(self):
        """TDD: No failure detected"""
        # Arrange
        ci_status = "success"

        # Act
        result = detect_failures(ci_status)

        # Assert
        assert result.status == "success"
        assert result.failure_detected is False


class TestStatusReporting:
    """TDD: Status Reporting"""

    def test_report_status_success(self):
        """TDD: Status report generated"""
        # Arrange
        ci_data = {"status": "success", "pipeline_id": "main"}

        # Act
        result = report_status(ci_data)

        # Assert
        assert result.status == "reported"
        assert "report" in result.dict()

    def test_report_status_failure(self):
        """TDD: Status report failed"""
        # Arrange
        ci_data = {}

        # Act
        result = report_status(ci_data)

        # Assert
        assert result.status == "failed"


class TestCIMonitorAgent:
    """Tests for the main CI Monitor Agent class"""

    def test_run_method_with_valid_context(self):
        """Test the main run method with valid context"""
        # Arrange
        context = CIContext(
            pipeline_id="test_pipeline",
            provider="github_actions",
            repo_url="https://github.com/example/repo",
        )
        agent = CIMonitorAgent()

        # Act & Assert
        # This test should expect that the GitHubClient is properly imported
        # Since we can't actually connect to GitHub in tests, we'll mock the client
        from unittest.mock import Mock, patch

        with patch.object(agent, "_get_ci_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            # Mock the get_pipeline_status method to return a test value
            mock_client.get_pipeline_status.return_value = "success"

            result = agent.run(context)

            # Assert
            assert result["status"] == "completed"
            assert "ci_status" in result
            assert "failure_detection" in result
            assert "status_report" in result

    def test_unsupported_provider_raises_error(self):
        """Test that unsupported provider raises ValueError"""
        # Arrange
        context = CIContext(
            pipeline_id="test_pipeline",
            provider="unsupported_provider",
            repo_url="https://github.com/example/repo",
        )
        agent = CIMonitorAgent()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            agent.run(context)

        assert "Unsupported CI provider" in str(exc_info.value)

    def test_detect_failures_method(self):
        """Test the detect_failures method directly"""
        # Arrange
        agent = CIMonitorAgent()

        # Test failure detection
        result = agent.detect_failures("failed", "test_pipeline")
        assert result.failure_detected is True
        assert result.status == "failure_detected"

        # Test no failure detection
        result = agent.detect_failures("success", "test_pipeline")
        assert result.failure_detected is False
        assert result.status == "success"

    def test_report_status_method(self):
        """Test the report_status method directly"""
        # Arrange
        agent = CIMonitorAgent()
        ci_data = {
            "pipeline_id": "test_pipeline",
            "ci_status": "success",
            "failure_detected": False,
            "failure_reason": None,
        }

        # Act
        result = agent.report_status(ci_data)

        # Assert
        assert result.status == "reported"
        assert result.report is not None
        assert result.report["pipeline_id"] == "test_pipeline"
