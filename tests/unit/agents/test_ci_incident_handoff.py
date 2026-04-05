from __future__ import annotations

from typing import Any

import agents.ci_incident_handoff as ci_incident_handoff_module
from agents.ci_incident_handoff import CiIncidentHandoff


def _artifact(result: dict) -> dict:
    artifacts = result.get("artifacts", [])
    assert artifacts
    return artifacts[0]["content"]


def test_ci_incident_handoff_mock_mode_creates_agent_opened_issue():
    agent = CiIncidentHandoff()
    result = agent.run(
        {
            "mock_mode": True,
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"id": 10, "status": "completed", "conclusion": "failure"},
        }
    )

    assert result["status"] == "SUCCESS"
    content = _artifact(result)
    assert content["created"] is True
    assert content["mock"] is True
    assert "agent:opened" in content["labels"]


def test_ci_incident_handoff_fails_without_repository():
    agent = CiIncidentHandoff()
    result = agent.run({"mock_mode": True})

    assert result["status"] == "FAILED"
    content = _artifact(result)
    assert content["created"] is False
    assert content["reason"] == "missing_repository_full_name"


def test_ci_incident_handoff_reuses_existing_open_issue(monkeypatch):
    class FakeGitHubClient:
        comment_calls: list[tuple[int, str]] = []
        update_calls: list[tuple[int, str]] = []

        def __init__(self, token: str, repo: str) -> None:
            self.token = token
            self.repo = repo
            self.create_calls = 0

        def list_issues(
            self,
            *,
            state: str = "open",
            labels: str | None = None,
            page: int = 1,
            per_page: int = 30,
        ) -> list[dict[str, Any]]:
            return [
                {
                    "number": 77,
                    "html_url": "https://github.com/acme/hordeforge/issues/77",
                    "title": "[CI Incident] acme/hordeforge run#123 failure",
                    "body": "existing incident",
                }
            ]

        def create_issue(
            self, title: str, body: str, labels: list[str] | None = None
        ) -> dict[str, Any]:
            self.create_calls += 1
            return {"number": 88, "html_url": "https://github.com/acme/hordeforge/issues/88"}

        def get_issue_comments(
            self,
            issue_number: int,
            *,
            page: int = 1,
            per_page: int = 30,
        ) -> list[dict[str, Any]]:
            return [
                {
                    "id": 101,
                    "body": "<!-- hordeforge:ci-incident-update -->\nold update body",
                }
            ]

        def comment_issue(self, issue_number: int, comment: str) -> dict[str, Any]:
            FakeGitHubClient.comment_calls.append((issue_number, comment))
            return {"id": 1}

        def update_issue_comment(self, comment_id: int, comment: str) -> dict[str, Any]:
            FakeGitHubClient.update_calls.append((comment_id, comment))
            return {"id": comment_id}

    monkeypatch.setattr(ci_incident_handoff_module, "GitHubClient", FakeGitHubClient)

    agent = CiIncidentHandoff()
    result = agent.run(
        {
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"id": 123, "status": "completed", "conclusion": "failure"},
            "github_token": "token",
        }
    )

    assert result["status"] == "SUCCESS"
    content = _artifact(result)
    assert content["created"] is False
    assert content["existing_issue"] is True
    assert content["enriched"] is True
    assert content["number"] == 77
    assert len(FakeGitHubClient.update_calls) == 1
    assert FakeGitHubClient.update_calls[0][0] == 101
    assert len(FakeGitHubClient.comment_calls) == 0


def test_ci_incident_handoff_mock_mode_preserves_candidate_files_and_targets():
    agent = CiIncidentHandoff()
    result = agent.run(
        {
            "mock_mode": True,
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"id": 10, "status": "completed", "conclusion": "failure"},
            "ci_failure_analyzer": {
                "artifacts": [
                    {
                        "type": "failure_analysis",
                        "content": {
                            "files": ["orchestrator/loader.py", "tests/unit/test_loader.py"],
                            "test_targets": ["tests/unit/test_loader.py::test_pipeline_load"],
                        },
                    }
                ]
            },
        }
    )

    assert result["status"] == "SUCCESS"
    content = _artifact(result)
    assert "orchestrator/loader.py" in content["files"]
    assert "tests/unit/test_loader.py::test_pipeline_load" in content["test_targets"]


def test_ci_incident_handoff_builds_rich_update_comment(monkeypatch):
    captured_comment: dict[str, str] = {}

    class FakeGitHubClient:
        def __init__(self, token: str, repo: str) -> None:
            self.token = token
            self.repo = repo

        def list_issues(
            self,
            *,
            state: str = "open",
            labels: str | None = None,
            page: int = 1,
            per_page: int = 30,
        ) -> list[dict[str, Any]]:
            return [
                {
                    "number": 77,
                    "html_url": "https://github.com/acme/hordeforge/issues/77",
                    "title": "[CI Incident] acme/hordeforge run#123 failure",
                    "body": "existing incident",
                }
            ]

        def get_issue_comments(
            self,
            issue_number: int,
            *,
            page: int = 1,
            per_page: int = 30,
        ) -> list[dict[str, Any]]:
            return [{"id": 101, "body": "<!-- hordeforge:ci-incident-update -->\nold"}]

        def update_issue_comment(self, comment_id: int, comment: str) -> dict[str, Any]:
            captured_comment["body"] = comment
            return {"id": comment_id}

        def comment_issue(self, issue_number: int, comment: str) -> dict[str, Any]:
            captured_comment["body"] = comment
            return {"id": 1}

    monkeypatch.setattr(ci_incident_handoff_module, "GitHubClient", FakeGitHubClient)

    agent = CiIncidentHandoff()
    result = agent.run(
        {
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"id": 123, "status": "completed", "conclusion": "failure"},
            "github_token": "token",
            "ci_failure_analyzer": {
                "artifacts": [
                    {
                        "type": "failure_analysis",
                        "content": {
                            "classification": "test_failure",
                            "severity": "major",
                            "language": "python",
                            "fingerprint": "abc123",
                            "files": ["tests/unit/test_loader.py", "orchestrator/loader.py"],
                            "test_targets": ["tests/unit/test_loader.py::test_pipeline_load"],
                            "details": [
                                {
                                    "name": "Test Unit",
                                    "reason": "pytest failed",
                                    "logs": "FAILED tests/unit/test_loader.py::test_pipeline_load",
                                }
                            ],
                        },
                    }
                ]
            },
        }
    )

    assert result["status"] == "SUCCESS"
    body = captured_comment["body"]
    assert "### Candidate Files" in body
    assert "### Test Targets" in body
    assert "tests/unit/test_loader.py::test_pipeline_load" in body
    assert "orchestrator/loader.py" in body