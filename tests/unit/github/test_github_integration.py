"""Unit tests for GitHub integration functionality."""

from unittest.mock import MagicMock

import pytest


class TestGitHubIntegration:
    """Tests for complete GitHub integration workflow."""

    def test_github_client_initialization(self):
        """Test GitHub client initialization with proper configuration."""
        from agents.github_client import GitHubClient

        client = GitHubClient(
            token="test_token",
            repo="test-owner/test-repo",
            max_retries=3,
            backoff_seconds=1.0,
            timeout_seconds=30.0,
        )

        assert client.repo == "test-owner/test-repo"
        assert client.api_url == "https://api.github.com/repos/test-owner/test-repo"
        assert client.max_retries == 3
        assert client.backoff_seconds == 1.0
        assert client.timeout_seconds == 30.0

        # Check headers contain proper authorization
        assert "Authorization" in client.headers
        assert "token test_token" in client.headers["Authorization"]

    def test_github_client_token_validation(self):
        """Test GitHub client token validation."""
        from agents.github_client import GitHubClient

        with pytest.raises(ValueError):
            GitHubClient(token="", repo="test-owner/test-repo")

        with pytest.raises(ValueError):
            GitHubClient(token="   ", repo="test-owner/test-repo")

    def test_github_client_methods_exist(self):
        """Test that GitHub client has required methods."""
        from agents.github_client import GitHubClient

        client = GitHubClient(token="test", repo="test/test")

        # Core issue methods
        assert hasattr(client, "get_issues")
        assert hasattr(client, "list_issues")
        assert hasattr(client, "create_issue")
        assert hasattr(client, "comment_issue")

        # Core PR methods
        assert hasattr(client, "get_pull_request")
        assert hasattr(client, "list_pull_requests")
        assert hasattr(client, "create_pr")
        assert hasattr(client, "merge_pull_request")
        assert hasattr(client, "submit_review")
        assert hasattr(client, "get_pull_request_reviews")

        # Core file methods
        assert hasattr(client, "get_file_content")
        assert hasattr(client, "create_or_update_file")
        assert hasattr(client, "delete_file")

        # Core branch methods
        assert hasattr(client, "get_branch")
        assert hasattr(client, "list_branches")
        assert hasattr(client, "create_branch")
        assert hasattr(client, "delete_branch")

    def test_dod_extractor_with_github_issue(self):
        """Test DoD extractor with GitHub issue format."""
        from agents.dod_extractor import parse_issue

        # Sample GitHub issue data
        issue_data = {
            "title": "Fix login authentication bug",
            "body": """
            ## Description
            The login authentication is failing for valid credentials.
            
            ## Acceptance Criteria
            - [ ] User can login with valid credentials
            - [ ] Error message shown for invalid credentials
            - [ ] Password validation works correctly
            
            ## Steps to Reproduce
            1. Enter valid username and password
            2. Click login button
            3. Observe authentication failure
            """,
            "labels": [{"name": "bug"}, {"name": "high-priority"}],
        }

        # Parse the issue
        parsed_issue = parse_issue(issue_data)

        assert parsed_issue.title == "Fix login authentication bug"
        assert "authentication" in parsed_issue.description.lower()
        assert len(parsed_issue.acceptance_criteria) >= 1
        # Check that at least one of the expected criteria is found
        found_expected = any(
            "login with valid credentials" in ac.lower()
            or "user can login with valid credentials" in ac.lower()
            for ac in parsed_issue.acceptance_criteria
        )
        assert found_expected, (
            f"Expected login criteria not found in {parsed_issue.acceptance_criteria}"
        )
        assert "bug" in parsed_issue.labels
        assert "high-priority" in parsed_issue.labels

    def test_dod_extractor_run_with_github_context(self):
        """Test DoD extractor agent with GitHub issue context."""
        from agents.dod_extractor import DodExtractor

        extractor = DodExtractor()

        context = {
            "issue": {
                "title": "Implement user registration",
                "body": "Need to implement user registration flow.\n\nAcceptance:\n- [x] Form validation\n- [x] Email verification",
                "labels": ["feature", "backend"],
            }
        }

        result = extractor.run(context)

        assert result["status"] in ["SUCCESS", "PARTIAL_SUCCESS"]

        # В новой версии агента результаты находятся в artifacts
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0

        dod_artifact = None
        for artifact in artifacts:
            if artifact.get("type") == "dod":
                dod_artifact = artifact
                break

        assert dod_artifact is not None
        content = dod_artifact.get("content", {})
        assert "acceptance_criteria" in content
        assert "bdd_scenarios" in content
        assert len(content["acceptance_criteria"]) >= 1

    def test_review_agent_with_github_context(self):
        """Test review agent with GitHub context."""
        from agents.review_agent import ReviewAgent

        agent = ReviewAgent()

        context = {
            "code_patch": {
                "files": [
                    {
                        "path": "auth/login.py",
                        "content": "def login(username, password):\n    return authenticate(username, password)",
                        "change_type": "modify",
                    }
                ]
            }
        }

        result = agent.run(context)

        assert "status" in result

        # В новой версии агента результаты находятся в artifacts
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0

        review_artifact = None
        for artifact in artifacts:
            if artifact.get("type") == "review_result":
                review_artifact = artifact
                break

        assert review_artifact is not None
        content = review_artifact.get("content", {})
        assert "decision" in content
        assert "policy_checks" in content
        assert content["decision"] in ["approve", "request_changes"]

    def test_review_agent_with_github_client(self):
        """Test review agent with live GitHub client."""
        from agents.review_agent import ReviewAgent

        agent = ReviewAgent()

        # Mock GitHub client
        mock_client = MagicMock()
        mock_client.get_pull_request_files.return_value = [
            {
                "filename": "auth/login.py",
                "patch": "+ def login(username, password):\n+    return authenticate(username, password)",
                "binary_file": False,
            }
        ]

        context = {"github_client": mock_client, "pr_number": 123, "code_patch": {"files": []}}

        result = agent.run(context)

        assert "status" in result
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0

        content = artifacts[0].get("content", {})
        assert content.get("live_review") is True
        assert "findings" in content

    def test_pr_merge_agent_with_github_context(self):
        """Test PR merge agent with GitHub context."""
        from agents.pr_merge_agent import PrMergeAgent

        agent = PrMergeAgent()

        context = {"review_result": {"decision": "approve", "findings": []}}

        result = agent.run(context)

        assert "status" in result
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0

        content = artifacts[0].get("content", {})
        assert "merged" in content
        assert "dry_run" in content

    def test_pr_merge_agent_with_github_client(self):
        """Test PR merge agent with live GitHub client."""
        from agents.pr_merge_agent import PrMergeAgent

        agent = PrMergeAgent()

        # Mock GitHub client
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

        assert "status" in result
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0

        content = artifacts[0].get("content", {})
        assert content.get("live_merge") is True
        assert content.get("merged") is True
        assert mock_client.merge_pull_request.called

    def test_repo_connector_initialization(self):
        """Test repo connector agent initialization."""
        from agents.repo_connector import RepoConnector

        connector = RepoConnector()

        assert connector.name == "repo_connector"
        assert "Connects" in connector.description

    def test_repo_connector_extract_repo_name_https(self):
        """Test repo connector repo name extraction from HTTPS URL."""
        from agents.repo_connector import RepoConnector

        connector = RepoConnector()

        repo_name = connector._extract_repo_name("https://github.com/test-owner/test-repo.git")
        assert repo_name == "test-owner/test-repo"

        repo_name = connector._extract_repo_name("https://github.com/owner/repo")
        assert repo_name == "owner/repo"

    def test_repo_connector_extract_repo_name_ssh(self):
        """Test repo connector repo name extraction from SSH URL."""
        from agents.repo_connector import RepoConnector

        connector = RepoConnector()

        repo_name = connector._extract_repo_name("git@github.com:test-owner/test-repo.git")
        assert repo_name == "test-owner/test-repo"

    def test_github_client_error_handling(self):
        """Test GitHub client error handling."""
        from agents.github_client import (
            GitHubAuthError,
            GitHubNotFoundError,
            GitHubRateLimitError,
        )

        # Test that proper exception types exist
        assert GitHubNotFoundError
        assert GitHubAuthError
        assert GitHubRateLimitError

    def test_github_client_pagination(self):
        """Test GitHub client pagination functionality."""
        from agents.github_client import GitHubClient

        client = GitHubClient(token="test", repo="test/test")

        # Test that pagination methods exist
        assert hasattr(client, "_parse_link_header")
        assert hasattr(client, "_extract_page_info")
        assert hasattr(client, "_log_pagination")

        # Test pagination-enabled methods
        assert hasattr(client, "get_issues")
        assert hasattr(client, "list_pull_requests_paginated")
        assert hasattr(client, "get_commits")

    def test_github_client_workflow_methods(self):
        """Test GitHub client CI/CD workflow methods."""
        from agents.github_client import GitHubClient

        client = GitHubClient(token="test", repo="test/test")

        assert hasattr(client, "get_workflow_runs")
        assert hasattr(client, "dispatch_workflow")
        assert hasattr(client, "get_workflow_run")
        assert hasattr(client, "get_workflow_run_jobs")

    def test_github_client_branch_protection(self):
        """Test GitHub client branch protection methods."""
        from agents.github_client import GitHubClient

        client = GitHubClient(token="test", repo="test/test")

        assert hasattr(client, "get_protection_rules")
        assert hasattr(client, "get_mergeable_status")
        assert hasattr(client, "get_combined_status")


class TestGitHubIntegrationScenarios:
    """Integration scenarios for GitHub workflow."""

    def test_complete_issue_to_merge_workflow(self):
        """Test complete workflow from issue parsing to PR merge."""
        from agents.dod_extractor import DodExtractor, parse_issue
        from agents.pr_merge_agent import PrMergeAgent
        from agents.review_agent import ReviewAgent

        # Simulate the complete pipeline

        # 1. Parse GitHub issue
        issue_data = {
            "title": "Add user profile page",
            "body": "Create user profile page with edit functionality.\n\nAC:\n- [x] Display user info\n- [x] Allow editing",
            "labels": [{"name": "feature"}],
        }

        parsed_issue = parse_issue(issue_data)
        assert len(parsed_issue.acceptance_criteria) >= 1

        # 2. Generate DoD
        extractor = DodExtractor()
        dod_context = {"issue": issue_data}
        dod_result = extractor.run(dod_context)

        assert dod_result["status"] in ["SUCCESS", "PARTIAL_SUCCESS"]

        # В новой версии агента результаты находятся в artifacts
        artifacts = dod_result.get("artifacts", [])
        assert len(artifacts) > 0

        dod_artifact = None
        for artifact in artifacts:
            if artifact.get("type") == "dod":
                dod_artifact = artifact
                break

        assert dod_artifact is not None
        dod_content = dod_artifact.get("content", {})
        assert "acceptance_criteria" in dod_content

        # 3. Mock code generation and review
        review_context = {
            "code_patch": {
                "files": [
                    {
                        "path": "profile/views.py",
                        "content": "# Generated profile view code",
                        "change_type": "create",
                    }
                ]
            }
        }

        review_agent = ReviewAgent()
        review_result = review_agent.run(review_context)

        # В новой версии агента результаты находятся в artifacts
        review_artifacts = review_result.get("artifacts", [])
        assert len(review_artifacts) > 0

        review_artifact = None
        for artifact in review_artifacts:
            if artifact.get("type") == "review_result":
                review_artifact = artifact
                break

        assert review_artifact is not None
        review_content = review_artifact.get("content", {})
        assert "decision" in review_content

        # 4. Mock merge decision
        merge_context = {"review_result": review_content}
        merge_agent = PrMergeAgent()
        merge_result = merge_agent.run(merge_context)

        # В новой версии агента результаты находятся в artifacts
        merge_artifacts = merge_result.get("artifacts", [])
        assert len(merge_artifacts) > 0

        # Проверим, есть ли артефакты с информацией о мердже
        merge_content_found = False
        for artifact in merge_artifacts:
            content = artifact.get("content", {})
            if "merged" in content:
                merge_content_found = True
                break

        # Если не нашли в артефактах, проверим в content напрямую
        if not merge_content_found:
            # Проверим, есть ли информация о мердже в любом из артефактов
            for artifact in merge_artifacts:
                content = artifact.get("content", {})
                # Проверим, содержит ли контент информацию о мердже
                if any(
                    key in content for key in ["merged", "merge_error", "live_merge", "dry_run"]
                ):
                    merge_content_found = True
                    break

        assert merge_content_found, f"No merge information found in artifacts: {merge_artifacts}"

    def test_github_client_with_mock_responses(self):
        """Test GitHub client with mock responses."""
        # Skip this test if responses library is not available
        try:
            import responses
        except ImportError:
            pytest.skip("responses library not available")

        from agents.github_client import GitHubClient

        with responses.RequestsMock() as rsps:
            # Mock getting issues
            rsps.add(
                responses.GET,
                "https://api.github.com/repos/test-owner/test-repo/issues",
                json=[{"number": 1, "title": "Test issue"}],
                status=200,
            )

            client = GitHubClient(token="test_token", repo="test-owner/test-repo")
            result = client.list_issues()

            assert len(result) == 1
            assert result[0]["title"] == "Test issue"

    def test_error_handling_in_github_integration(self):
        """Test error handling across GitHub integration components."""
        from agents.github_client import GitHubClient

        # Test that exceptions are properly propagated
        client_instance = GitHubClient(token="test", repo="test/test")

        # Verify that the client has proper error types
        assert hasattr(client_instance, "_build_api_error")
        assert hasattr(client_instance, "_is_rate_limit_403")


def test_github_integration_smoke():
    """Smoke test for GitHub integration."""
    # Just test that all components can be imported without error
    from agents.dod_extractor import DodExtractor
    from agents.github_client import GitHubClient
    from agents.pr_merge_agent import PrMergeAgent
    from agents.repo_connector import RepoConnector
    from agents.review_agent import ReviewAgent

    assert GitHubClient
    assert DodExtractor
    assert ReviewAgent
    assert PrMergeAgent
    assert RepoConnector


if __name__ == "__main__":
    pytest.main([__file__])
