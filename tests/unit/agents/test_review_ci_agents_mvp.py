from agents.ci_failure_analyzer import CiFailureAnalyzer
from agents.issue_closer import IssueCloser
from agents.pr_merge_agent import PrMergeAgent
from agents.review_agent import ReviewAgent


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    raise AssertionError(f"Artifact not found: {artifact_type}")


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def test_review_agent_returns_decision_with_policy_checks():
    agent = ReviewAgent()
    context = {
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {
                "schema_version": "1.0",
                "files": [{"path": "src/app.py", "diff": "+print('ok')"}],
            },
        )
    }

    result = agent.run(context)

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    review = _artifact_content(result, "review_result")
    assert review["decision"] in {"approve", "request_changes"}
    assert "policy_checks" in review


def test_pr_merge_agent_returns_merge_decision_in_dry_run():
    agent = PrMergeAgent()
    context = {
        "review_agent": _step_result(
            "SUCCESS",
            "review_result",
            {"decision": "approve", "policy_checks": {"has_changes": True}},
        )
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    merge_status = _artifact_content(result, "merge_status")
    assert merge_status["dry_run"] is True
    assert merge_status["merged"] is True


def test_ci_failure_analyzer_parses_mock_ci_input_and_classifies_failure():
    agent = CiFailureAnalyzer()
    result = agent.run(
        {
            "ci_run": {
                "status": "failed",
                "failed_jobs": [{"name": "unit-tests", "reason": "assertion failed"}],
            },
            "repository": {"full_name": "acme/hordeforge"},
        }
    )

    assert result["status"] == "SUCCESS"
    analysis = _artifact_content(result, "failure_analysis")
    assert analysis["classification"] in {
        "test_failure",
        "build_failure",
        "infrastructure",
        "unknown",
    }
    assert analysis["failed_jobs_count"] == 1


def test_issue_closer_returns_close_decision_when_ci_is_green():
    agent = IssueCloser()
    context = {
        "ci_verification": {
            "status": "SUCCESS",
            "test_results": {"total": 5, "passed": 5, "failed": 0},
            "artifacts": [
                {"type": "test_results", "content": {"total": 5, "passed": 5, "failed": 0}}
            ],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    close_status = _artifact_content(result, "close_status")
    assert close_status["close_issue"] is True
