# tests/unit/agents/test_review_agent.py

from agents.review_agent import run_lint, run_security_scan, validate_architecture_rules


class TestLintChecks:
    """TDD: Lint Checks"""

    def test_run_lint(self):
        """TDD: Run lint checks"""
        # Arrange
        project = "python"

        # Act
        result = run_lint(project)

        # Assert
        assert result["tool"] == "ruff"


class TestSecurityScan:
    """TDD: Security Scan"""

    def test_run_security_scan(self):
        """TDD: Run security scan"""
        # Arrange
        project = "python"

        # Act
        result = run_security_scan(project)

        # Assert
        assert result["tool"] == "bandit"


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
