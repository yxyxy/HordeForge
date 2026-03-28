from __future__ import annotations

import logging
from typing import Any

import pytest
import requests

from agents.github_client import (
    GitHubApiError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubValidationError,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        json_body: Any | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.headers = headers or {}
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._json_body


class ScriptedSession:
    def __init__(self, events: list[Any]) -> None:
        self.events = list(events)
        self.calls: list[dict[str, Any]] = []

    def request(  # noqa: A003
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None,
        params: dict[str, Any] | None,
        timeout: float,
    ) -> Any:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "params": params,
                "timeout": timeout,
            }
        )
        if not self.events:
            raise AssertionError("No scripted events left for request().")
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


def _make_client(
    events: list[Any],
    *,
    max_retries: int = 0,
    backoff_seconds: float = 0.0,
) -> tuple[GitHubClient, ScriptedSession]:
    session = ScriptedSession(events)
    client = GitHubClient(
        token="secret-token",
        repo="acme/hordeforge",
        session=session,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout_seconds=3.0,
    )
    return client, session


def test_create_issue_returns_json_payload_on_success():
    client, session = _make_client([FakeResponse(201, json_body={"id": 101, "title": "Bug fix"})])

    result = client.create_issue("Bug fix", "Fix regression", labels=["bug"])

    assert result["id"] == 101
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"].endswith("/issues")
    assert session.calls[0]["json"]["labels"] == ["bug"]


def test_get_branch_sha_raises_typed_not_found_error():
    client, _ = _make_client([FakeResponse(404, json_body={"message": "Not Found"})])

    with pytest.raises(GitHubNotFoundError) as error:
        client.get_branch_sha("missing-branch")

    assert error.value.status_code == 404
    assert "Not Found" in str(error.value)


def test_create_issue_raises_validation_error_and_includes_body_details():
    client, _ = _make_client(
        [
            FakeResponse(
                422,
                json_body={"message": "Validation Failed", "errors": [{"field": "title"}]},
            )
        ]
    )

    with pytest.raises(GitHubValidationError) as error:
        client.create_issue("", "Body")

    assert error.value.status_code == 422
    assert "Validation Failed" in str(error.value)
    assert "title" in str(error.value)


def test_request_retries_on_server_error_and_logs_attempt_count(monkeypatch, caplog):
    sleep_calls: list[float] = []
    monkeypatch.setattr("agents.github_client.time.sleep", lambda value: sleep_calls.append(value))
    client, session = _make_client(
        [
            FakeResponse(502, json_body={"message": "Bad gateway"}),
            FakeResponse(200, json_body={"workflow_runs": []}),
        ],
        max_retries=2,
        backoff_seconds=0.25,
    )

    with caplog.at_level(logging.WARNING, logger="hordeforge.github_client"):
        result = client.get_workflow_runs("ci.yaml")

    assert result["workflow_runs"] == []
    assert len(session.calls) == 2
    assert sleep_calls == [0.25]
    assert any("github_request_retry" in record.message for record in caplog.records)
    assert any("attempt=1" in record.message for record in caplog.records)


def test_request_retries_on_transport_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("agents.github_client.time.sleep", lambda _value: None)
    client, session = _make_client(
        [
            requests.Timeout("network timeout"),
            FakeResponse(200, json_body={"workflow_runs": []}),
        ],
        max_retries=1,
        backoff_seconds=0.01,
    )

    result = client.get_workflow_runs("ci.yaml")

    assert result["workflow_runs"] == []
    assert len(session.calls) == 2


def test_request_raises_rate_limit_error_after_retry_exhausted(monkeypatch):
    sleep_calls: list[float] = []
    monkeypatch.setattr("agents.github_client.time.sleep", lambda value: sleep_calls.append(value))
    client, session = _make_client(
        [
            FakeResponse(
                429,
                json_body={"message": "API rate limit exceeded"},
                headers={"Retry-After": "1"},
            ),
            FakeResponse(
                429,
                json_body={"message": "API rate limit exceeded"},
                headers={"Retry-After": "1"},
            ),
        ],
        max_retries=1,
        backoff_seconds=0.1,
    )

    with pytest.raises(GitHubRateLimitError) as error:
        client.create_pr("Fix", "fix-branch")

    assert error.value.status_code == 429
    assert error.value.retryable is True
    assert len(session.calls) == 2
    assert sleep_calls == [1.0]


def test_non_json_error_body_is_reported_as_api_error():
    client, _ = _make_client(
        [
            FakeResponse(
                400,
                json_body=None,
                text="Bad Request from proxy",
                json_error=ValueError("invalid json"),
            )
        ]
    )

    with pytest.raises(GitHubApiError) as error:
        client.comment_issue(1, "hello")

    assert error.value.status_code == 400
    assert "Bad Request from proxy" in str(error.value)


# =========================================================================
# Pagination Tests (HF-P6-001)
# =========================================================================


def test_parse_link_header():
    """Test Link header parsing."""
    client, _ = _make_client([])

    response = FakeResponse(
        200,
        json_body={"items": []},
        headers={
            "Link": '<https://api.github.com/repos/yxyxy/hordeforge/issues?page=2>; rel="next", <https://api.github.com/repos/yxyxy/hordeforge/issues?page=1>; rel="first"'
        },
    )

    links = client._parse_link_header(response)
    assert links["next"] == "https://api.github.com/repos/yxyxy/hordeforge/issues?page=2"
    assert links["first"] == "https://api.github.com/repos/yxyxy/hordeforge/issues?page=1"


def test_parse_link_header_empty():
    """Test Link header parsing with no Link header."""
    client, _ = _make_client([])

    response = FakeResponse(200, json_body={"items": []}, headers={})
    links = client._parse_link_header(response)
    assert links == {}


def test_extract_page_info():
    """Test page info extraction from headers."""
    client, _ = _make_client([])

    response = FakeResponse(
        200,
        json_body={"items": []},
        headers={
            "Link": '<https://api.github.com/repos/yxyxy/hordeforge/issues?page=2&per_page=50>; rel="next"',
            "X-Total-Count": "150",
        },
    )

    info = client._extract_page_info(response)
    assert info["has_next"] is True
    assert info["has_prev"] is False
    assert info["total"] == 150
    assert info["per_page"] == 50
    assert info["current_page"] == 2


def test_get_issues_with_pagination():
    """Test get_issues with pagination parameters."""
    client, session = _make_client(
        [
            FakeResponse(200, json_body=[{"id": 1, "title": "Issue 1"}]),
            FakeResponse(
                200,
                json_body=[{"id": 1, "title": "Issue 1"}],
                headers={
                    "Link": '<https://api.github.com/repos/yxyxy/hordeforge/issues?page=2&per_page=30>; rel="next"',
                    "X-Total-Count": "60",
                },
            ),
        ]
    )

    result = client.get_issues(page=1, per_page=30)

    assert "issues" in result
    assert "pagination" in result
    assert result["pagination"]["current_page"] == 2
    assert result["pagination"]["has_next"] is True
    assert result["pagination"]["total"] == 60


def test_get_issues_validates_per_page_limit():
    """Test that per_page > 100 raises validation error."""
    client, _ = _make_client([])

    with pytest.raises(GitHubValidationError) as error:
        client.get_issues(per_page=101)

    assert "cannot exceed 100" in str(error.value)


def test_list_pull_requests_with_pagination():
    """Test list_pull_requests with pagination."""
    client, session = _make_client(
        [
            FakeResponse(200, json_body=[{"id": 1, "title": "PR 1"}]),
            FakeResponse(
                200,
                json_body=[{"id": 1, "title": "PR 1"}],
                headers={
                    "Link": '<https://api.github.com/repos/yxyxy/hordeforge/pulls?page=2&per_page=30>; rel="next"',
                },
            ),
        ]
    )

    result = client.list_pull_requests_paginated(page=1, per_page=30)

    assert "pulls" in result
    assert "pagination" in result


def test_get_commits_with_pagination():
    """Test get_commits with pagination parameters."""
    client, session = _make_client(
        [
            FakeResponse(200, json_body=[{"sha": "abc123"}]),
            FakeResponse(
                200,
                json_body=[{"sha": "abc123"}],
                headers={
                    "Link": '<https://api.github.com/repos/yxyxy/hordeforge/commits?page=2&per_page=30>; rel="next"',
                    "X-Total-Count": "100",
                },
            ),
        ]
    )

    result = client.get_commits(page=1, per_page=30)

    assert "commits" in result
    assert "pagination" in result
    assert result["pagination"]["total"] == 100


def test_get_commits_validates_per_page_limit():
    """Test that per_page > 100 raises validation error."""
    client, _ = _make_client([])

    with pytest.raises(GitHubValidationError) as error:
        client.get_commits(per_page=101)

    assert "cannot exceed 100" in str(error.value)


def test_list_pull_requests_uses_pagination():
    """Test that list_pull_requests calls paginated version."""
    client, session = _make_client(
        [
            FakeResponse(200, json_body=[{"id": 1, "title": "PR 1"}]),
            FakeResponse(
                200,
                json_body=[{"id": 1, "title": "PR 1"}],
                headers={"Link": '<url>; rel="next"'},
            ),
        ]
    )

    result = client.list_pull_requests(state="open", page=1, per_page=30)

    assert isinstance(result, list)
    assert len(session.calls) >= 1
    assert session.calls[0]["params"]["page"] == 1
    assert session.calls[0]["params"]["per_page"] == 30
