"""TDD: PR Merge Agent tests"""

import agents.pr_merge_agent as pr_merge_agent_module
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
        pr = {"checks": ["ci", "lint"], "status": "success"}
        result = validate_branch_protection(pr)
        assert result is True


class TestMergeQueueManagement:
    """TDD: Merge Queue Management"""

    def test_add_pr_to_queue(self):
        queue = []
        pr = {"id": 1}
        queue = add_to_queue(queue, pr)
        assert len(queue) == 1

    def test_merge_next_pr(self):
        queue = [{"id": 1}, {"id": 2}]
        merged, queue = process_queue(queue)
        assert merged["id"] == 1


class TestRebaseHandling:
    """TDD: Rebase Handling"""

    def test_rebase_required(self):
        pr = {"behind": True}
        result = handle_rebase(pr)
        assert result == "rebase"

    def test_rebase_not_required(self):
        pr = {"behind": False}
        result = handle_rebase(pr)
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
                "live_merge": True,
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

    def test_creates_pr_in_merge_agent_when_publish_enabled(self, monkeypatch):
        class FakeGitHubClient:
            def __init__(self):
                self.updated_labels = []
                self.comments = []

            def update_issue_labels(self, issue_number: int, labels: list[str]):
                self.updated_labels.append((issue_number, labels))
                return {"number": issue_number, "labels": labels}

            def comment_issue(self, issue_number: int, comment: str):
                self.comments.append((issue_number, comment))
                return {"issue_number": issue_number, "body": comment}

        class FakeWorkflowResult:
            success = True
            pr_url = "https://github.com/acme/hordeforge/pull/77"
            pr_number = 77
            branch_name = "horde/10-fix"
            error = None

        class FakePatchWorkflow:
            def __init__(self, github_client):
                self.github_client = github_client

            def apply_patch(self, files, pr_title, pr_body, branch_name):
                return FakeWorkflowResult()

        monkeypatch.setattr(pr_merge_agent_module, "PatchWorkflowOrchestrator", FakePatchWorkflow)

        client = FakeGitHubClient()
        agent = PrMergeAgent()
        result = agent.run(
            {
                "github_client": client,
                "publish_pr_in_merge_agent": True,
                "live_merge": False,
                "issue": {
                    "number": 10,
                    "title": "Fix CI",
                    "labels": [{"name": "agent:planning"}],
                },
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
                    "artifacts": [
                        {
                            "type": "code_patch",
                            "content": {
                                "files": [
                                    {
                                        "path": "src/feature_impl.py",
                                        "change_type": "modify",
                                        "content": "# fix",
                                    }
                                ]
                            },
                        }
                    ],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert content["pr_created"] is True
        assert content["pr_number"] == 77
        assert content["pr_url"] == "https://github.com/acme/hordeforge/pull/77"
        assert content["merged"] is False
        assert content["dry_run"] is True
        assert client.updated_labels
        assert client.comments

    def test_creates_pr_even_when_review_not_approved_if_publish_enabled(self, monkeypatch):
        class FakeGitHubClient:
            def __init__(self):
                self.updated_labels = []
                self.comments = []

            def update_issue_labels(self, issue_number: int, labels: list[str]):
                self.updated_labels.append((issue_number, labels))
                return {"number": issue_number, "labels": labels}

            def comment_issue(self, issue_number: int, comment: str):
                self.comments.append((issue_number, comment))
                return {"issue_number": issue_number, "body": comment}

        class FakeWorkflowResult:
            success = True
            pr_url = "https://github.com/acme/hordeforge/pull/88"
            pr_number = 88
            branch_name = "horde/10-fix"
            error = None

        class FakePatchWorkflow:
            def __init__(self, github_client):
                self.github_client = github_client

            def apply_patch(self, files, pr_title, pr_body, branch_name):
                return FakeWorkflowResult()

        monkeypatch.setattr(pr_merge_agent_module, "PatchWorkflowOrchestrator", FakePatchWorkflow)

        client = FakeGitHubClient()
        agent = PrMergeAgent()
        result = agent.run(
            {
                "github_client": client,
                "publish_pr_in_merge_agent": True,
                "live_merge": False,
                "issue": {
                    "number": 10,
                    "title": "Fix CI",
                    "labels": [{"name": "agent:planning"}],
                },
                "review_agent": {
                    "status": "PARTIAL_SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "request_changes"}}],
                },
                "test_runner": {
                    "status": "PARTIAL_SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 2}}],
                },
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [
                        {
                            "type": "code_patch",
                            "content": {
                                "files": [
                                    {
                                        "path": "src/feature_impl.py",
                                        "change_type": "modify",
                                        "content": "# fix",
                                    }
                                ]
                            },
                        }
                    ],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert content["pr_created"] is True
        assert content["pr_number"] == 88
        assert content["merged"] is False
        assert content["dry_run"] is True
        assert "review_not_approved" in content["reason"]
        assert "tests_not_passed" in content["reason"]

    def test_uses_existing_pr_url_from_patch(self):
        agent = PrMergeAgent()
        result = agent.run(
            {
                "review_agent": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "review_result", "content": {"decision": "approve"}}],
                },
                "test_runner": {
                    "status": "SUCCESS",
                    "artifacts": [{"type": "test_results", "content": {"failed": 0, "exit_code": 0}}],
                },
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [
                        {
                            "type": "code_patch",
                            "content": {
                                "pr_number": 55,
                                "pr_url": "https://github.com/acme/hordeforge/pull/55",
                                "files": [],
                            },
                        }
                    ],
                },
            }
        )

        content = result["artifacts"][0]["content"]
        assert content["pr_number"] == 55
        assert content["pr_url"] == "https://github.com/acme/hordeforge/pull/55"
        assert "pr_missing" not in content["reason"]