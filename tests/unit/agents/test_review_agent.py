# tests/unit/agents/test_review_agent.py

from subprocess import CompletedProcess

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
        """TDD: Run lint checks"""
        # Arrange
        project = "python"
        recorded: dict[str, object] = {}

        def _fake_run(cmd, capture_output, text, cwd):
            recorded["cmd"] = cmd
            recorded["cwd"] = cwd
            return CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("agents.review_agent.subprocess.run", _fake_run)

        # Act
        result = run_lint(project)

        # Assert
        assert result["tool"] == "ruff"
        assert result["success"] is True
        assert recorded["cmd"] == ["ruff", "check", "."]
        assert recorded["cwd"] == "."


class TestSecurityScan:
    """TDD: Security Scan"""

    def test_run_security_scan(self, monkeypatch):
        """TDD: Run security scan"""
        # Arrange
        project = "python"
        recorded: dict[str, object] = {}

        def _fake_run(cmd, capture_output, text, cwd):
            recorded["cmd"] = cmd
            recorded["cwd"] = cwd
            return CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("agents.review_agent.subprocess.run", _fake_run)

        # Act
        result = run_security_scan(project)

        # Assert
        assert result["tool"] == "bandit"
        assert result["success"] is True
        assert recorded["cmd"] == ["bandit", "-r", "."]
        assert recorded["cwd"] == "."


class TestArchitectureRulesValidation:
    """TDD: Architecture Rules Validation"""

    def test_validate_architecture_rules(self):
        """TDD: Validate architecture rules"""
        # Arrange
        dependencies = ["module_a -> module_b"]

        # Act
        result = validate_architecture_rules(dependencies)

        # Assert
        assert result is not None


class TestReviewOutputParsing:
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
