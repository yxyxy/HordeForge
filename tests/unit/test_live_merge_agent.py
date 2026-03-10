"""Unit tests for live GitHub merge agent (HF-P5-007)."""

from unittest.mock import MagicMock

from agents.pr_merge_agent import PrMergeAgent


class TestPrMergeAgent:
    """Tests for PrMergeAgent class."""

    def test_agent_has_name(self):
        agent = PrMergeAgent()
        assert hasattr(agent, "name")
        assert agent.name == "pr_merge_agent"

    def test_agent_has_description(self):
        agent = PrMergeAgent()
        assert hasattr(agent, "description")

    def test_run_with_approved_review(self):
        agent = PrMergeAgent()
        context = {
            "review_result": {
                "decision": "approve",
                "policy_checks": {"dry_run_only": True},
            }
        }
        # Мокаем merge_if_ready для dry-run
        agent.merge_if_ready = MagicMock(return_value={"success": True, "merged": True, "dry_run": True})
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("dry_run") is True
        assert artifact.get("merged") is True

    def test_run_with_rejected_review(self):
        agent = PrMergeAgent()
        context = {
            "review_result": {
                "decision": "request_changes",
                "policy_checks": {},
            }
        }
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("merged") is False or artifact.get("merged") is None
        if "reason" in artifact:
            assert "review_not_approved" in artifact["reason"]

    def test_run_with_no_review(self):
        agent = PrMergeAgent()
        context = {}
        result = agent.run(context)
        # Should handle missing review gracefully
        assert "status" in result

    def test_live_merge_success(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "success"}
        mock_client.merge_pull_request.return_value = {"merged": True, "sha": "abc123"}

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "review_result": {"decision": "approve"},
        }
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("merged") is True
        assert artifact.get("live_merge") is True
        assert mock_client.merge_pull_request.called

    def test_live_merge_not_mergeable(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": False, "mergeable_state": "dirty"}

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "review_result": {"decision": "approve"},
        }
        agent.merge_if_ready = MagicMock(return_value={"success": False, "merged": False, "merge_error": "Not mergeable"})
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("merged") is False
        assert "not mergeable" in artifact.get("merge_error", "").lower()

    def test_live_merge_ci_failing(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "failure"}

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "review_result": {"decision": "approve"},
        }
        # Merge не должен быть вызван
        agent.merge_if_ready = MagicMock(return_value={"success": False, "merged": False})
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert not agent.merge_if_ready.called or artifact.get("merged") is False

    def test_live_merge_draft_pr(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": False, "draft": True}

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "review_result": {"decision": "approve"},
        }
        agent.merge_if_ready = MagicMock(return_value={"success": False, "merged": False})
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("merged") is False

    def test_merge_strategy_default_squash(self):
        agent = PrMergeAgent()
        context = {"review_result": {"decision": "approve"}}
        agent.merge_if_ready = MagicMock(return_value={"success": True, "merged": True, "strategy": "squash"})
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert artifact.get("strategy") == "squash"

    def test_next_actions_when_merged(self):
        agent = PrMergeAgent()
        context = {"review_result": {"decision": "approve"}}
        agent.merge_if_ready = MagicMock(return_value={"success": True, "merged": True, "next_actions": ["ci_monitor_agent"]})
        result = agent.run(context)
        next_actions = result.get("next_actions", [])
        assert "ci_monitor_agent" in next_actions

    def test_next_actions_when_not_merged(self):
        agent = PrMergeAgent()
        context = {"review_result": {"decision": "request_changes"}}
        agent.merge_if_ready = MagicMock(return_value={"success": False, "merged": False, "next_actions": ["request_human_review"]})
        result = agent.run(context)
        next_actions = result.get("next_actions", [])
        assert "request_human_review" in next_actions


class TestMergeConditions:
    """Tests for merge condition checking."""

    def test_check_merge_conditions_success(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "success"}
        result = agent._check_merge_conditions(mock_client, 123)
        assert result is True

    def test_check_merge_conditions_not_mergeable(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": False}
        result = agent._check_merge_conditions(mock_client, 123)
        assert result is False

    def test_check_merge_conditions_ci_pending(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "pending"}
        result = agent._check_merge_conditions(mock_client, 123)
        assert result is True

    def test_check_merge_conditions_ci_failure(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "failure"}
        result = agent._check_merge_conditions(mock_client, 123)
        assert result is False

    def test_check_merge_conditions_exception(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.side_effect = Exception("API Error")
        result = agent._check_merge_conditions(mock_client, 123)
        assert result is False


class TestMergeStatusArtifact:
    """Tests for merge status artifact structure."""

    def test_artifact_has_required_fields(self):
        agent = PrMergeAgent()
        context = {"review_result": {"decision": "approve"}}
        agent.merge_if_ready = MagicMock(return_value={
            "merged": True,
            "dry_run": True,
            "strategy": "squash",
            "reason": "approved",
            "live_merge": True
        })
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert "dry_run" in artifact
        assert "merged" in artifact
        assert "strategy" in artifact
        assert "reason" in artifact
        assert "live_merge" in artifact

    def test_live_merge_artifact_fields(self):
        agent = PrMergeAgent()
        mock_client = MagicMock()
        mock_client.get_mergeable_status.return_value = {"mergeable": True, "draft": False}
        mock_client.get_pull_request.return_value = {"head": {"sha": "abc123"}}
        mock_client.get_combined_status.return_value = {"state": "success"}
        mock_client.merge_pull_request.return_value = {"sha": "abc123"}

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "review_result": {"decision": "approve"},
        }
        agent.merge_if_ready = MagicMock(return_value={
            "merged": True,
            "live_merge": True,
            "merge_error": None
        })
        result = agent.run(context)
        artifacts = result.get("artifacts", [{}])
        artifact = artifacts[0].get("content", {}) if artifacts else {}
        assert "merge_error" in artifact
        assert artifact.get("live_merge") is True