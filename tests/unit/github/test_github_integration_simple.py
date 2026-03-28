"""Simple unit tests for GitHub integration functionality that avoid circular imports."""

import pytest


def test_github_client_can_be_imported():
    """Test that GitHub client can be imported directly."""
    from agents.github_client import GitHubClient

    assert GitHubClient


def test_github_client_initialization():
    """Test GitHub client initialization."""
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


def test_github_client_token_validation():
    """Test GitHub client token validation."""
    from agents.github_client import GitHubClient

    with pytest.raises(ValueError):
        GitHubClient(token="", repo="test-owner/test-repo")

    with pytest.raises(ValueError):
        GitHubClient(token="   ", repo="test-owner/test-repo")


def test_github_client_methods_exist():
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


def test_github_client_error_types_exist():
    """Test that GitHub client error types exist."""
    from agents.github_client import (
        GitHubApiError,
        GitHubAuthError,
        GitHubNotFoundError,
        GitHubRateLimitError,
        GitHubServerError,
        GitHubTransportError,
        GitHubValidationError,
    )

    # Test that exception classes can be instantiated
    assert GitHubNotFoundError
    assert GitHubAuthError
    assert GitHubRateLimitError
    assert GitHubValidationError
    assert GitHubApiError
    assert GitHubServerError
    assert GitHubTransportError


def test_dod_extractor_can_be_imported():
    """Test that DoD extractor can be imported directly."""
    from agents.dod_extractor import DodExtractor, parse_issue

    assert DodExtractor
    assert parse_issue


def test_dod_extractor_with_github_issue():
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


def test_review_agent_can_be_imported():
    """Test that review agent can be imported directly."""
    from agents.review_agent import ReviewAgent

    assert ReviewAgent


def test_pr_merge_agent_can_be_imported():
    """Test that PR merge agent can be imported directly."""
    from agents.pr_merge_agent import PrMergeAgent

    assert PrMergeAgent


def test_repo_connector_can_be_imported():
    """Test that repo connector can be imported directly."""
    from agents.repo_connector import RepoConnector

    assert RepoConnector


def test_github_client_pagination_methods():
    """Test that GitHub client has pagination methods."""
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


def test_github_client_workflow_methods():
    """Test that GitHub client has CI/CD workflow methods."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    assert hasattr(client, "get_workflow_runs")
    assert hasattr(client, "dispatch_workflow")
    assert hasattr(client, "get_workflow_run")
    assert hasattr(client, "get_workflow_run_jobs")


def test_github_client_branch_protection_methods():
    """Test that GitHub client has branch protection methods."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    assert hasattr(client, "get_protection_rules")
    assert hasattr(client, "get_mergeable_status")
    assert hasattr(client, "get_combined_status")


def test_github_client_merge_functionality():
    """Test GitHub client merge functionality."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test merge-related methods exist
    assert hasattr(client, "merge_pull_request")
    assert hasattr(client, "get_mergeable_status")
    assert hasattr(client, "get_combined_status")


def test_github_client_file_operations():
    """Test GitHub client file operations."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test file operation methods exist
    assert hasattr(client, "get_file_content")
    assert hasattr(client, "create_or_update_file")
    assert hasattr(client, "delete_file")


def test_github_client_branch_operations():
    """Test GitHub client branch operations."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test branch operation methods exist
    assert hasattr(client, "get_branch")
    assert hasattr(client, "list_branches")
    assert hasattr(client, "create_branch")
    assert hasattr(client, "delete_branch")


def test_github_client_pull_request_operations():
    """Test GitHub client pull request operations."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test PR operation methods exist
    assert hasattr(client, "get_pull_request")
    assert hasattr(client, "get_pull_request_reviews")
    assert hasattr(client, "get_pull_request_files")
    assert hasattr(client, "get_pull_request_diff")
    assert hasattr(client, "create_review_comment")
    assert hasattr(client, "submit_review")


def test_github_client_create_issue():
    """Test GitHub client create issue functionality."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test create issue method exists
    assert hasattr(client, "create_issue")
    assert hasattr(client, "comment_issue")


def test_github_client_error_handling():
    """Test GitHub client error handling methods."""
    from agents.github_client import GitHubClient

    client = GitHubClient(token="test", repo="test/test")

    # Test error handling methods exist
    assert hasattr(client, "_build_api_error")
    assert hasattr(client, "_is_rate_limit_403")
    assert hasattr(client, "_is_success_status")
    assert hasattr(client, "_is_transient_status")


if __name__ == "__main__":
    pytest.main([__file__])
