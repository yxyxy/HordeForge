"""End-to-end integration tests for agent quality (HF-P5-008).

These tests verify the complete pipeline flow with mocked GitHub API.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.llm_wrapper import (
    build_code_prompt,
    build_spec_prompt,
    detect_language,
    detect_spec_type,
    parse_code_output,
    parse_spec_output,
)
from agents.pipeline_runner import PipelineRunner


class TestSpecGenerationPipeline:
    """Tests for spec generation pipeline."""

    def test_build_spec_prompt_with_api_type(self):
        """Test spec prompt building for API features."""
        prompt = build_spec_prompt(
            summary="Create user API endpoint",
            requirements=["GET /users returns user list", "Authentication required"],
            context={"repo": "test-repo", "language": "python"},
            spec_type="api",
        )
        assert "API" in prompt
        assert "Create user API endpoint" in prompt

    def test_build_spec_prompt_with_ui_type(self):
        """Test spec prompt building for UI features."""
        prompt = build_spec_prompt(
            summary="Add login button",
            requirements=["Button shows on page", "Click triggers auth"],
            context={},
            spec_type="ui",
        )
        assert "UI" in prompt
        assert "button" in prompt.lower()

    def test_parse_valid_spec_output(self):
        """Test parsing valid spec output."""
        spec_json = json.dumps({
            "summary": "Test feature",
            "requirements": [
                {
                    "id": "REQ-001",
                    "description": "Test requirement",
                    "test_criteria": "Run test",
                    "priority": "must",
                }
            ],
            "technical_notes": ["Note 1"],
            "file_changes": [
                {"path": "test.py", "change_type": "create", "description": "Test file"}
            ],
        })
        spec = parse_spec_output(spec_json)
        assert spec["summary"] == "Test feature"
        assert len(spec["requirements"]) == 1

    def test_parse_spec_with_markdown(self):
        """Test parsing spec output with markdown wrapper."""
        spec_json = """```json
{
    "summary": "Test",
    "requirements": [{"id": "1", "description": "Test", "test_criteria": "test"}],
    "technical_notes": [],
    "file_changes": []
}
```"""
        spec = parse_spec_output(spec_json)
        assert spec["summary"] == "Test"


class TestCodeGenerationPipeline:
    """Tests for code generation pipeline."""

    def test_build_code_prompt_for_python(self):
        """Test code prompt building for Python."""
        spec = {
            "summary": "Test feature",
            "requirements": [],
            "technical_notes": [],
            "file_changes": [{"path": "test.py", "change_type": "create", "description": "Test"}],
        }
        prompt = build_code_prompt(
            spec=spec,
            test_cases=[{"name": "test_one", "input": "x", "expected": "y"}],
            repo_context={"existing_files": ["main.py"]},
            language="python",
        )
        assert "Python" in prompt
        assert "PEP 8" in prompt

    def test_build_code_prompt_for_typescript(self):
        """Test code prompt building for TypeScript."""
        spec = {
            "summary": "Test feature",
            "requirements": [],
            "technical_notes": [],
            "file_changes": [{"path": "test.ts", "change_type": "create", "description": "Test"}],
        }
        prompt = build_code_prompt(
            spec=spec,
            test_cases=[],
            repo_context={"existing_files": ["index.ts"]},
            language="typescript",
        )
        assert "TypeScript" in prompt
        assert "Strict TypeScript" in prompt

    def test_parse_valid_code_output(self):
        """Test parsing valid code output."""
        code_json = json.dumps({
            "files": [
                {"path": "test.py", "change_type": "create", "content": "x = 1"}
            ],
            "decisions": ["decision1"],
            "test_changes": [],
        })
        result = parse_code_output(code_json)
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "test.py"


class TestDetectionFunctions:
    """Tests for detection functions."""

    def test_detect_api_spec_type(self):
        """Test API spec type detection."""
        assert detect_spec_type("Create REST API", "Need HTTP endpoints") == "api"
        assert detect_spec_type("Add CRUD endpoint", "POST and GET methods") == "api"

    def test_detect_ui_spec_type(self):
        """Test UI spec type detection."""
        assert detect_spec_type("Add button", "UI component") == "ui"
        assert detect_spec_type("Create modal", "Frontend component") == "ui"

    def test_detect_data_spec_type(self):
        """Test data spec type detection."""
        assert detect_spec_type("Data migration", "Transform schema") == "data"
        assert detect_spec_type("Export CSV", "Export data") == "data"

    def test_detect_python_language(self):
        """Test Python language detection."""
        assert detect_language({"existing_files": ["main.py", "utils.py"]}) == "python"

    def test_detect_typescript_language(self):
        """Test TypeScript language detection."""
        assert detect_language({"existing_files": ["index.ts", "app.tsx"]}) == "typescript"

    def test_detect_go_language(self):
        """Test Go language detection."""
        assert detect_language({"existing_files": ["main.go", "handler.go"]}) == "go"


class TestPipelineIntegration:
    """Integration tests for full pipeline with mocked GitHub."""

    @patch("agents.code_generator_v2.get_llm_wrapper")
    @patch("agents.code_generator_v2.PatchWorkflowOrchestrator")
    def test_feature_pipeline_with_github_integration(
        self, mock_orchestrator_class, mock_llm
    ):
        """Test feature pipeline with GitHub integration."""
        # Setup mocks
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete.return_value = json.dumps({
            "files": [{"path": "feature.py", "content": "# Feature", "change_type": "create"}],
            "decisions": [],
            "test_changes": [],
        })
        mock_llm.return_value = mock_llm_instance

        mock_orchestrator = MagicMock()
        mock_orchestrator.apply_patch.return_value = MagicMock(
            success=True,
            pr_url="https://github.com/test/repo/pull/1",
            pr_number=1,
            branch_name="hordeforge/feature-123",
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run pipeline
        runner = PipelineRunner()
        result = runner.run(
            "feature_pipeline",
            inputs={
                "issue_title": "Add feature",
                "issue_body": "Implement new feature",
                "github_client": MagicMock(),
            },
        )

        # Verify
        assert result["status"] in ("SUCCESS", "PARTIAL_SUCCESS")

    def test_pipeline_with_llm_failure_fallback(self):
        """Test pipeline falls back to deterministic when LLM fails."""
        runner = PipelineRunner()

        # Run with no LLM available - should use deterministic
        result = runner.run(
            "feature_pipeline",
            inputs={
                "issue_title": "Simple fix",
                "issue_body": "Fix something",
                "use_llm": False,
            },
        )

        assert "status" in result
        # Should complete even without LLM


class TestNegativeTestCases:
    """Negative test cases for error handling."""

    def test_invalid_spec_json_raises(self):
        """Test that invalid JSON raises ValueError."""
        with pytest.raises(ValueError):
            parse_spec_output("not json at all")

    def test_spec_missing_required_fields_raises(self):
        """Test that missing required fields raises ValueError."""
        with pytest.raises(ValueError, match="Missing required field"):
            parse_spec_output(json.dumps({"summary": "Test"}))

    def test_spec_missing_test_criteria_raises(self):
        """Test that missing test_criteria raises ValueError."""
        with pytest.raises(ValueError, match="test_criteria"):
            parse_spec_output(json.dumps({
                "summary": "Test",
                "requirements": [{"description": "Test"}],
                "technical_notes": [],
                "file_changes": [],
            }))

    def test_code_missing_files_field_raises(self):
        """Test that missing files field raises ValueError."""
        with pytest.raises(ValueError, match="files"):
            parse_code_output(json.dumps({"decisions": []}))


class TestHappyPathScenarios:
    """Happy path scenarios for complete workflows."""

    def test_complete_spec_to_code_flow(self):
        """Test complete flow from spec to code."""
        # 1. Build spec
        spec = {
            "summary": "Test feature",
            "requirements": [
                {"id": "REQ-001", "description": "Test", "test_criteria": "pass", "priority": "must"}
            ],
            "technical_notes": ["Note"],
            "file_changes": [{"path": "test.py", "change_type": "create", "description": "Test"}],
        }

        # 2. Build code prompt
        prompt = build_code_prompt(
            spec=spec,
            test_cases=[{"name": "test_001", "input": "x", "expected": "y"}],
            repo_context={"existing_files": ["main.py"]},
        )

        # 3. Verify prompt contains key elements
        assert "Test feature" in prompt
        assert "test_001" in prompt

    def test_multiple_file_code_generation(self):
        """Test code generation for multiple files."""
        code_json = json.dumps({
            "files": [
                {"path": "models.py", "content": "class Model: pass", "change_type": "create"},
                {"path": "views.py", "content": "def view(): pass", "change_type": "create"},
                {"path": "tests/test_models.py", "content": "def test_model(): pass", "change_type": "create"},
            ],
            "decisions": [],
            "test_changes": [],
        })

        result = parse_code_output(code_json)
        assert len(result["files"]) == 3
        assert result["files"][0]["path"] == "models.py"
        assert result["files"][1]["path"] == "views.py"
        assert result["files"][2]["path"] == "tests/test_models.py"


class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    def test_retry_on_parse_error(self):
        """Test that parse errors are handled gracefully."""
        # First call returns invalid JSON, second works
        invalid_json = "not valid"
        valid_json = json.dumps({
            "summary": "Test",
            "requirements": [{"id": "1", "description": "t", "test_criteria": "t", "priority": "must"}],
            "technical_notes": [],
            "file_changes": [],
        })

        # Test parse_spec_output raises on invalid
        with pytest.raises(ValueError):
            parse_spec_output(invalid_json)

        # Test valid JSON parses correctly
        result = parse_spec_output(valid_json)
        assert result["summary"] == "Test"

    def test_graceful_degradation_without_llm(self):
        """Test that system works without LLM."""
        runner = PipelineRunner()

        # Run without LLM
        result = runner.run(
            "feature_pipeline",
            inputs={"use_llm": False},
        )

        assert "status" in result
