from agents.context_utils import get_artifact_from_result
from agents.issue_closer import IssueCloser, close_issue, verify_ci, verify_dod


class TestDoDVerification:
    """TDD: DoD Verification"""

    def test_dod_passed(self):
        """TDD: DoD met"""
        # Arrange
        dod = {"dod": ["tests"], "checked": ["tests"]}

        # Act
        result = verify_dod(dod)

        # Assert
        assert result == "passed"

    def test_dod_failed(self):
        """TDD: DoD not met"""
        # Arrange
        dod = {"dod": ["tests"], "checked": []}

        # Act
        result = verify_dod(dod)

        # Assert
        assert result == "failed"

    def test_dod_multiple_items_all_checked(self):
        """TDD: Multiple DoD items all checked"""
        # Arrange
        dod = {"dod": ["tests", "docs", "review"], "checked": ["tests", "docs", "review"]}

        # Act
        result = verify_dod(dod)

        # Assert
        assert result == "passed"

    def test_dod_multiple_items_missing_one(self):
        """TDD: Multiple DoD items with one missing"""
        # Arrange
        dod = {"dod": ["tests", "docs", "review"], "checked": ["tests", "docs"]}

        # Act
        result = verify_dod(dod)

        # Assert
        assert result == "failed"


class TestCIVerification:
    """TDD: CI Verification"""

    def test_ci_passed(self):
        """TDD: CI passed"""
        # Arrange
        status = "success"

        # Act
        result = verify_ci(status)

        # Assert
        assert result == "passed"

    def test_ci_failed(self):
        """TDD: CI failed"""
        # Arrange
        status = "failed"

        # Act
        result = verify_ci(status)

        # Assert
        assert result == "failed"

    def test_ci_pending(self):
        """TDD: CI pending"""
        # Arrange
        status = "pending"

        # Act
        result = verify_ci(status)

        # Assert
        assert result == "failed"

    def test_ci_case_insensitive_success(self):
        """TDD: CI success in different case"""
        # Arrange
        status = "SUCCESS"

        # Act
        result = verify_ci(status)

        # Assert
        assert result == "passed"


class TestIssueClosure:
    """TDD: Issue Closure"""

    def test_close_issue_success(self):
        """TDD: Close issue after DoD and CI passed"""
        # Arrange
        dod_result = "passed"
        ci_result = "passed"
        issue_id = 123

        # Act
        result = close_issue(issue_id, dod_result, ci_result)

        # Assert
        assert result["status"] == "closed"
        assert result["issue_id"] == issue_id

    def test_close_issue_dod_failed(self):
        """TDD: Do not close issue when DoD failed"""
        # Arrange
        dod_result = "failed"
        ci_result = "passed"
        issue_id = 123

        # Act
        result = close_issue(issue_id, dod_result, ci_result)

        # Assert
        assert result["status"] == "open"
        assert result["reason"] == "DoD verification failed"

    def test_close_issue_ci_failed(self):
        """TDD: Do not close issue when CI failed"""
        # Arrange
        dod_result = "passed"
        ci_result = "failed"
        issue_id = 123

        # Act
        result = close_issue(issue_id, dod_result, ci_result)

        # Assert
        assert result["status"] == "open"
        assert result["reason"] == "CI verification failed"

    def test_close_issue_both_failed(self):
        """TDD: Do not close issue when both DoD and CI failed"""
        # Arrange
        dod_result = "failed"
        ci_result = "failed"
        issue_id = 123

        # Act
        result = close_issue(issue_id, dod_result, ci_result)

        # Assert
        assert result["status"] == "open"
        assert result["reason"] == "DoD verification failed"


class TestIssueCloserAgent:
    """TDD: Issue Closer Agent Integration"""

    def test_agent_closes_issue_when_dod_and_ci_passed(self):
        """TDD: Agent closes issue when both DoD and CI passed"""
        # Arrange
        agent = IssueCloser()
        context = {
            "issue_id": 123,
            "dod": {"dod": ["tests"], "checked": ["tests"]},
            "ci_status": "success",
        }

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        artifact_content = get_artifact_from_result(result, "issue_closure_result")
        assert artifact_content is not None
        assert artifact_content["final_status"] == "closed"
        assert artifact_content["dod_result"] == "passed"
        assert artifact_content["ci_result"] == "passed"

    def test_agent_keeps_issue_open_when_dod_failed(self):
        """TDD: Agent keeps issue open when DoD failed"""
        # Arrange
        agent = IssueCloser()
        context = {
            "issue_id": 123,
            "dod": {"dod": ["tests"], "checked": []},
            "ci_status": "success",
        }

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "PARTIAL_SUCCESS"
        artifact_content = get_artifact_from_result(result, "issue_closure_result")
        assert artifact_content is not None
        assert artifact_content["final_status"] == "open"
        assert artifact_content["dod_result"] == "failed"
        assert artifact_content["ci_result"] == "passed"

    def test_agent_keeps_issue_open_when_ci_failed(self):
        """TDD: Agent keeps issue open when CI failed"""
        # Arrange
        agent = IssueCloser()
        context = {
            "issue_id": 123,
            "dod": {"dod": ["tests"], "checked": ["tests"]},
            "ci_status": "failed",
        }

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "PARTIAL_SUCCESS"
        artifact_content = get_artifact_from_result(result, "issue_closure_result")
        assert artifact_content is not None
        assert artifact_content["final_status"] == "open"
        assert artifact_content["dod_result"] == "passed"
