from subprocess import CompletedProcess

from agents.llm_wrapper import parse_review_output as parse_review_output_centralized
from agents.review_agent import (
    ReviewAgent,
    parse_review_output,
    run_lint,
    run_security_scan,
    validate_architecture_rules,
)


class TestLintChecks:
    """TDD: Lint Checks"""

    def test_run_lint(self, monkeypatch):
        project = "python"
        recorded: dict[str, object] = {}

        def _fake_run(cmd, capture_output, text, cwd):
            recorded["cmd"] = cmd
            recorded["cwd"] = cwd
            return CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("agents.review_agent.subprocess.run", _fake_run)

        result = run_lint(project)

        assert result["tool"] == "ruff"
        assert result["success"] is True
        assert recorded["cmd"] == ["ruff", "check", "."]
        assert recorded["cwd"] == "."


class TestSecurityScan:
    """TDD: Security Scan"""

    def test_run_security_scan(self, monkeypatch):
        project = "python"
        recorded: dict[str, object] = {}

        def _fake_run(cmd, capture_output, text, cwd):
            recorded["cmd"] = cmd
            recorded["cwd"] = cwd
            return CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("agents.review_agent.subprocess.run", _fake_run)

        result = run_security_scan(project)

        assert result["tool"] == "bandit"
        assert result["success"] is True
        assert recorded["cmd"] == ["bandit", "-r", "."]
        assert recorded["cwd"] == "."


class TestArchitectureRulesValidation:
    """TDD: Architecture Rules Validation"""

    def test_validate_architecture_rules(self):
        dependencies = ["module_a -> module_b"]
        result = validate_architecture_rules(dependencies)
        assert result is not None


class TestReviewOutputParsing:
    def test_centralized_parse_review_output_accepts_dict_and_decision_alias(self):
        payload = {
            "decision": "approve",
            "summary": "Structured response",
            "findings": [],
            "strengths": ["ok"],
            "recommendations": ["none"],
            "confidence": 0.7,
        }
        parsed = parse_review_output_centralized(payload)
        assert parsed["overall_decision"] == "approve"

    def test_parse_review_output_accepts_dict_input(self):
        payload = {
            "overall_decision": "approve",
            "summary": "Structured response",
            "findings": [],
            "strengths": ["ok"],
            "recommendations": ["none"],
            "confidence": 0.7,
        }
        parsed = parse_review_output(payload)
        assert parsed["overall_decision"] == "approve"

    def test_parse_review_output_handles_markdown_json_block(self):
        payload = """
```json
{
  "overall_decision": "approve",
  "summary": "Looks good",
  "findings": [],
  "strengths": ["clear changes"],
  "recommendations": ["add one more test"],
  "confidence": 0.9
}
```
""".strip()
        parsed = parse_review_output(payload)
        assert parsed["overall_decision"] == "approve"
        assert parsed["confidence"] == 0.9

    def test_parse_review_output_handles_prefixed_text(self):
        payload = """
Review result:
{
  "overall_decision": "request_changes",
  "summary": "Found one issue",
  "findings": [
    {
      "file": "app.py",
      "line": 12,
      "type": "bug",
      "severity": "high",
      "description": "Potential crash",
      "suggestion": "Handle None",
      "category": "logic_error"
    }
  ],
  "strengths": ["good structure"],
  "recommendations": ["add guard checks"],
  "confidence": 0.8
}
Thanks.
""".strip()
        parsed = parse_review_output(payload)
        assert parsed["overall_decision"] == "request_changes"
        assert len(parsed["findings"]) == 1

    def test_centralized_parse_review_output_accepts_overall_decision_aliases(self):
        payload = {
            "overallDecision": "approve",
            "summary": "Structured response",
            "findings": [],
            "strengths": ["ok"],
            "recommendations": ["none"],
            "confidence": 0.7,
        }
        parsed = parse_review_output_centralized(payload)
        assert parsed["overall_decision"] == "approve"


def test_review_agent_fails_when_llm_required_and_unavailable(monkeypatch):
    class _FailingWrapper:
        def complete(self, prompt: str):
            raise RuntimeError("llm unavailable")

        def close(self):
            return None

    monkeypatch.setattr(
        "agents.review_agent.get_llm_wrapper", lambda *args, **kwargs: _FailingWrapper()
    )

    context = {
        "use_llm": True,
        "require_llm": True,
        "code_generator": {
            "artifacts": [
                {
                    "type": "code_patch",
                    "content": {"files": [{"path": "src/a.py", "content": "print('x')"}]},
                }
            ]
        },
    }

    result = ReviewAgent().run(context)

    assert result["status"] == "FAILED"
    assert result["artifacts"][0]["type"] == "review_result"


def test_review_agent_detects_grounding_mismatch():
    context = {
        "use_llm": False,
        "code_generator": {
            "artifacts": [
                {
                    "type": "code_patch",
                    "content": {
                        "files": [
                            {
                                "path": "src/unrelated.py",
                                "content": "print('x')",
                                "change_type": "modify",
                            }
                        ]
                    },
                }
            ]
        },
        "ci_failure_analysis": {
            "artifacts": [
                {
                    "type": "ci_failure_context",
                    "content": {
                        "files": ["orchestrator/loader.py"],
                        "test_targets": ["tests/unit/test_loader.py::test_ok"],
                    },
                }
            ]
        },
    }

    result = ReviewAgent().run(context)

    assert result["status"] == "PARTIAL_SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["decision"] == "request_changes"
    assert any(item["type"] == "grounding_mismatch" for item in artifact["findings"])


def test_review_agent_detects_invalid_verification_for_path_error():
    context = {
        "use_llm": False,
        "code_generator": {
            "artifacts": [
                {
                    "type": "code_patch",
                    "content": {
                        "files": [
                            {
                                "path": "tests/unit/test_loader.py",
                                "content": "def test_x(): assert True",
                                "change_type": "modify",
                            }
                        ]
                    },
                }
            ]
        },
        "test_runner": {
            "artifacts": [
                {
                    "type": "test_results",
                    "content": {
                        "exit_code": 4,
                        "failed": 0,
                        "error_classification": "path_error",
                        "stderr": "ERROR: file or directory not found",
                    },
                }
            ]
        },
    }

    result = ReviewAgent().run(context)

    assert result["status"] == "PARTIAL_SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["decision"] == "request_changes"
    assert any(item["type"] == "verification_invalid" for item in artifact["findings"])
    assert any(
        "rerun verification" in item.lower() or "test execution" in item.lower()
        for item in artifact["recommendations"]
    )


def test_review_agent_approves_clean_patch_without_ci_constraints():
    context = {
        "use_llm": False,
        "code_generator": {
            "artifacts": [
                {
                    "type": "code_patch",
                    "content": {
                        "files": [
                            {
                                "path": "orchestrator/loader.py",
                                "content": "def load():\n    return True\n",
                                "change_type": "modify",
                            }
                        ]
                    },
                }
            ]
        },
        "test_runner": {
            "artifacts": [
                {
                    "type": "test_results",
                    "content": {
                        "exit_code": 0,
                        "failed": 0,
                    },
                }
            ]
        },
    }

    result = ReviewAgent().run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["decision"] == "approve"
    assert artifact["policy_checks"]["grounding_checked"] is True
    assert artifact["policy_checks"]["verification_checked"] is True
