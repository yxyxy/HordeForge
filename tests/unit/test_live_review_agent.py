"""Unit tests for live GitHub review agent (HF-P5-006)."""

from unittest.mock import MagicMock

from agents.review_agent import (
    SECURITY_PATTERNS,
    ReviewAgent,
    analyze_file_content,
)


class TestSecurityPatternDetection:
    """Tests for security pattern detection."""

    def test_detect_hardcoded_password(self):
        """Test detection of hardcoded passwords."""
        content = 'password = "secret123"'
        findings = analyze_file_content("config.py", content)
        assert any("password" in f["message"].lower() for f in findings)

    def test_detect_hardcoded_api_key(self):
        """Test detection of hardcoded API keys."""
        content = 'api_key = "sk-1234567890abcdef"'
        findings = analyze_file_content("app.py", content)
        assert any("api key" in f["message"].lower() for f in findings)

    def test_detect_hardcoded_secret(self):
        """Test detection of hardcoded secrets."""
        content = 'secret = "my-super-secret-key"'
        findings = analyze_file_content("config.py", content)
        assert any("secret" in f["message"].lower() for f in findings)

    def test_detect_command_injection(self):
        """Test detection of command injection risks."""
        content = 'os.execute(f"ls {user_input}")'
        findings = analyze_file_content("utils.py", content)
        assert any("injection" in f["message"].lower() for f in findings)

    def test_detect_format_string_vulnerability(self):
        """Test detection of format string vulnerabilities."""
        content = '"Hello %s" % user_input'
        findings = analyze_file_content("app.py", content)
        assert any("format" in f["message"].lower() for f in findings)

    def test_no_finding_when_clean(self):
        """Test no findings for clean code."""
        content = """
def process_data(data):
    result = transform(data)
    return result
"""
        findings = analyze_file_content("app.py", content)
        assert len(findings) == 0


class TestStylePatternDetection:
    """Tests for style pattern detection."""

    def test_detect_wildcard_import(self):
        """Test detection of wildcard imports."""
        content = "from os import *"
        findings = analyze_file_content("app.py", content)
        assert any("wildcard import" in f["message"].lower() for f in findings)

    def test_detect_multiple_imports(self):
        """Test detection of multiple imports on one line."""
        content = "import os, sys, json"
        findings = analyze_file_content("app.py", content)
        assert any("multiple imports" in f["message"].lower() for f in findings)

    def test_clean_style(self):
        """Test no style findings for clean code."""
        content = """
import os
import sys

def main():
    pass
"""
        findings = analyze_file_content("app.py", content)
        style_findings = [f for f in findings if f["type"] == "style"]
        assert len(style_findings) == 0


class TestAnalyzeFileContent:
    """Tests for analyze_file_content function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        result = analyze_file_content("test.py", "x = 1")
        assert isinstance(result, list)

    def test_file_path_in_finding(self):
        """Test that file path is included in findings."""
        content = 'password = "secret"'
        findings = analyze_file_content("config.py", content)
        assert any(f["file"] == "config.py" for f in findings)

    def test_severity_levels(self):
        """Test that severity levels are assigned correctly."""
        content = 'password = "secret"'
        findings = analyze_file_content("config.py", content)
        assert any(f["severity"] == "high" for f in findings)

        content = "from os import *"
        findings = analyze_file_content("app.py", content)
        assert any(f["severity"] == "low" for f in findings)


class TestSecurityPatterns:
    """Tests for security pattern definitions."""

    def test_password_pattern_defined(self):
        """Test that password pattern is defined."""
        assert any("password" in p[1].lower() for p in SECURITY_PATTERNS)

    def test_api_key_pattern_defined(self):
        """Test that API key pattern is defined."""
        assert any("api" in p[1].lower() for p in SECURITY_PATTERNS)

    def test_command_injection_pattern_defined(self):
        """Test that command injection pattern is defined."""
        assert any("injection" in p[1].lower() for p in SECURITY_PATTERNS)


class TestReviewAgent:
    """Tests for ReviewAgent class."""

    def test_agent_has_name(self):
        """Test that agent has name."""
        agent = ReviewAgent()
        assert hasattr(agent, "name")
        assert agent.name == "review_agent"

    def test_agent_has_description(self):
        """Test that agent has description."""
        agent = ReviewAgent()
        assert hasattr(agent, "description")

    def test_run_with_no_github_client(self):
        """Test run without GitHub client (local analysis)."""
        agent = ReviewAgent()
        context = {
            "code_patch": {
                "files": [
                    {"path": "test.py", "content": "x = 1", "change_type": "create"}
                ]
            }
        }
        result = agent.run(context)

        assert result["status"] in ("SUCCESS", "PARTIAL_SUCCESS")
        # Check artifact structure
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        assert artifacts[0]["type"] == "review_result"

    def test_run_with_empty_patch(self):
        """Test run with empty patch."""
        agent = ReviewAgent()
        context = {"code_patch": {"files": []}}
        result = agent.run(context)

        # Should still return a result
        assert "status" in result
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        artifact = artifacts[0].get("content", {})
        assert "policy_checks" in artifact

    def test_run_with_github_client(self):
        """Test run with GitHub client (live review)."""
        agent = ReviewAgent()

        # Mock GitHub client
        mock_client = MagicMock()
        mock_client.get_pull_request_files.return_value = [
            {"filename": "test.py", "patch": "+ x = 1", "binary_file": False}
        ]

        context = {
            "github_client": mock_client,
            "pr_number": 123,
            "code_patch": {"files": []},
        }

        agent.run(context)

        # Should attempt to fetch PR files
        assert mock_client.get_pull_request_files.called

    def test_finding_severity_logic(self):
        """Test that critical findings change decision."""
        agent = ReviewAgent()
        context = {
            "code_patch": {
                "files": [
                    {"path": "config.py", "content": 'password = "secret123"', "change_type": "create"}
                ]
            }
        }
        result = agent.run(context)

        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        artifact = artifacts[0].get("content", {})
        # With security finding, should request changes
        assert artifact.get("decision") == "request_changes"


class TestReviewAgentIntegration:
    """Integration tests for review agent with mocked GitHub."""

    def test_local_analysis_fallback(self):
        """Test that local analysis is used when no GitHub client."""
        agent = ReviewAgent()
        context = {
            "code_patch": {
                "files": [
                    {"path": "utils.py", "content": "def test(): pass", "change_type": "create"}
                ]
            }
        }

        result = agent.run(context)
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        artifact = artifacts[0].get("content", {})

        # Should indicate dry run
        assert artifact.get("policy_checks", {}).get("dry_run_only") is True
        assert artifact.get("live_review") is False

    def test_policy_checks_structure(self):
        """Test that policy checks are properly structured."""
        agent = ReviewAgent()
        context = {"code_patch": {"files": [{"path": "x.py", "content": "x=1", "change_type": "create"}]}}

        result = agent.run(context)
        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        artifact = artifacts[0].get("content", {})

        policy_checks = artifact.get("policy_checks", {})
        assert "has_changes" in policy_checks
        assert "touches_protected_branch" in policy_checks
        assert "dry_run_only" in policy_checks
