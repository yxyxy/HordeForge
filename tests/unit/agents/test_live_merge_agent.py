"""Unit tests for pr_merge_agent."""

from unittest.mock import MagicMock

from agents.pr_merge_agent import PrMergeAgent


class TestPrMergeAgent:
    def test_agent_has_name(self):
        agent = PrMergeAgent()
        assert agent.name == "pr_merge_agent"

    def test_dry_run_blocked_when_pr_missing(self):
        agent = PrMergeAgent()
        result = agent.run(
            {
                "review_result": {"decision": "approve"},
                "test_results": {"failed": 0},
            }
        )
        artifact = result["artifacts"][0]["content"]
        assert result["status"] == "PARTIAL_SUCCESS"
        assert artifact["dry_run"] is True
        assert artifact["merged"] is False
        assert "pr_missing" in artifact["reason"]

    def test_live_merge_success(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "success"}
        mock_client.merge_pull_request.return_value = {"merged": True, "sha": "abc123"}

        result = agent.run(
            {
                "github_client": mock_client,
                "pr_number": 123,
                "review_result": {"decision": "approve"},
                "test_results": {"failed": 0},
            }
        )

        artifact = result["artifacts"][0]["content"]
        assert result["status"] == "SUCCESS"
        assert artifact["merged"] is True
        assert artifact["live_merge"] is True
        assert artifact["dry_run"] is False

    def test_live_merge_not_mergeable_sets_error(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {
            "mergeable": False,
            "mergeable_state": "dirty",
        }

        result = agent.run(
            {
                "github_client": mock_client,
                "pr_number": 123,
                "review_result": {"decision": "approve"},
                "test_results": {"failed": 0},
            }
        )

        artifact = result["artifacts"][0]["content"]
        assert artifact["merged"] is False
        assert "not mergeable" in (artifact.get("merge_error") or "").lower()

    def test_next_actions_when_not_merged(self):
        agent = PrMergeAgent()
        result = agent.run({"review_result": {"decision": "request_changes"}})
        assert "request_human_review" in result.get("next_actions", [])


class TestMergeConditions:
    def test_check_merge_conditions_success(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "success"}
        assert agent._check_merge_conditions(mock_client, 123) is True

    def test_check_merge_conditions_not_mergeable(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": False}
        assert agent._check_merge_conditions(mock_client, 123) is False

    def test_check_merge_conditions_ci_failure(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "failure"}
        assert agent._check_merge_conditions(mock_client, 123) is False

    def test_check_merge_conditions_exception(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.side_effect = Exception("API Error")
        assert agent._check_merge_conditions(mock_client, 123) is False
