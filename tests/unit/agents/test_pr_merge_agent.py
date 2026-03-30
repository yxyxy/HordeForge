"""TDD: PR Merge Agent tests"""

from agents.pr_merge_agent import (
    PrMergeAgent,
    add_to_queue,
    handle_rebase,
    process_queue,
    validate_branch_protection,
)


class TestBranchProtectionChecks:
    """TDD: Branch Protection Checks"""

    def test_validate_branch_protection(self):
        """TDD: Validate branch protection"""
        # Arrange
        pr = {"checks": ["ci", "lint"], "status": "success"}

        # Act
        result = validate_branch_protection(pr)

        # Assert
        assert result is True


class TestMergeQueueManagement:
    """TDD: Merge Queue Management"""

    def test_add_pr_to_queue(self):
        """TDD: Add PR to queue"""
        # Arrange
        queue = []
        pr = {"id": 1}

        # Act
        queue = add_to_queue(queue, pr)

        # Assert
        assert len(queue) == 1

    def test_merge_next_pr(self):
        """TDD: Merge next PR"""
        # Arrange
        queue = [{"id": 1}, {"id": 2}]

        # Act
        merged, queue = process_queue(queue)

        # Assert
        assert merged["id"] == 1


class TestRebaseHandling:
    """TDD: Rebase Handling"""

    def test_rebase_required(self):
        """TDD: Rebase required"""
        # Arrange
        pr = {"behind": True}

        # Act
        result = handle_rebase(pr)

        # Assert
        assert result == "rebase"

    def test_rebase_not_required(self):
        """TDD: Rebase not required"""
        # Arrange
        pr = {"behind": False}

        # Act
        result = handle_rebase(pr)

        # Assert
        assert result == "noop"


class TestPrMergeAgentGates:
    def test_dry_run_with_missing_pr_is_not_merged(self):
        agent = PrMergeAgent()
        result = agent.run(
            {
                "review_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "approve"}}],
                },
                "test_runner": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 0}}],
                },
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "code_patch", "content": {}}],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert result["status"] == "PARTIAL_SUCCESS"
        assert content["merged"] is False
        assert content["dry_run"] is True
        assert "pr_missing" in content["reason"]

    def test_live_merge_runs_only_when_all_gates_pass(self):
        class FakeGitHubClient:
            def get_mergeable_status(self, pr_number: int) -> dict:
                return {"mergeable": True, "draft": False}

            def get_pull_request(self, pr_number: int) -> dict:
                return {"head": {"sha": "abc"}}

            def get_combined_status(self, head_sha: str) -> dict:
                return {"state": "success"}

            def merge_pull_request(self, pr_number: int, merge_method: str = "squash") -> dict:
                return {"merged": True}

        agent = PrMergeAgent()
        result = agent.run(
            {
                "github_client": FakeGitHubClient(),
                "pr_number": 42,
                "review_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "approve"}}],
                },
                "test_runner": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 0}}],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert result["status"] == "SUCCESS"
        assert content["merged"] is True
        assert content["dry_run"] is False

    def test_pr_number_falls_back_to_code_generator_patch(self):
        agent = PrMergeAgent()
        result = agent.run(
            {
                "review_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "approve"}}],
                },
                "test_runner": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 0}}],
                },
                "fix_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "code_patch", "content": {}}],
                },
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "code_patch", "content": {"pr_number": 123}}],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert content["pr_number"] == 123
        assert "pr_missing" not in content["reason"]

    def test_pr_number_falls_back_when_top_level_code_patch_is_from_fix_agent(self):
        agent = PrMergeAgent()
        result = agent.run(
            {
                "review_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "approve"}}],
                },
                "test_runner": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 0}}],
                },
                # Typical runtime alias that may point to the latest patch (fix_agent),
                # which does not include PR metadata.
                "code_patch": {"schema_version": "1.0", "files": [], "fix_iteration": 1},
                "fix_agent": {
                    "status": "SUCCESS",
                    "artifacts": [
                        {"type": "code_patch", "content": {"schema_version": "1.0", "files": []}}
                    ],
                },
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "code_patch", "content": {"pr_number": 321}}],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert content["pr_number"] == 321
        assert "pr_missing" not in content["reason"]
