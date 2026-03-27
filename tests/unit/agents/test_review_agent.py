# tests/unit/agents/test_review_agent.py

from subprocess import CompletedProcess

from agents.review_agent import run_lint, run_security_scan, validate_architecture_rules


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
