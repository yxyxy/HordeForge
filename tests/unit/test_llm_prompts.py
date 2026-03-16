"""Unit tests for LLM prompt engineering (HF-P5-001, HF-P5-002)."""

import json
from unittest.mock import MagicMock

import pytest

from agents.llm_wrapper import (
    LANGUAGE_STANDARDS,
    SPEC_TYPES,
    build_code_prompt,
    build_spec_prompt,
    # Code generation
    detect_language,
    # Spec generation
    detect_spec_type,
    generate_code_with_retry,
    generate_spec_with_retry,
    parse_code_output,
    parse_spec_output,
)


class TestSpecTypeDetection:
    """Tests for spec type detection."""

    def test_detect_api_type(self):
        """Test API type detection from keywords."""
        assert detect_spec_type("Create REST API endpoint", "Need an API for users") == "api"
        assert detect_spec_type("Add CRUD endpoint", "HTTP POST and GET") == "api"

    def test_detect_ui_type(self):
        """Test UI type detection from keywords."""
        assert detect_spec_type("Add login button", "UI component for login") == "ui"
        assert detect_spec_type("Create modal dialog", "New frontend component") == "ui"

    def test_detect_data_type(self):
        """Test data type detection from keywords."""
        assert detect_spec_type("Data migration", "Transform data to new schema") == "data"
        assert detect_spec_type("Export to CSV", "Export data from database") == "data"

    def test_default_to_backend(self):
        """Test default fallback to backend type."""
        result = detect_spec_type("Fix bug", "Something is broken")
        assert result in SPEC_TYPES


class TestBuildSpecPrompt:
    """Tests for spec prompt building."""

    def test_basic_spec_prompt(self):
        """Test basic spec prompt generation."""
        prompt = build_spec_prompt(
            summary="Add user authentication",
            requirements=["Implement login", "Implement logout"],
            context={"repo": "test-repo"},
        )
        assert "Add user authentication" in prompt
        assert "Implement login" in prompt
        assert "test-repo" in prompt

    def test_spec_type_api(self):
        """Test API spec type template."""
        prompt = build_spec_prompt(
            summary="Add API endpoint",
            requirements=["GET /users"],
            context={},
            spec_type="api",
        )
        assert "API" in prompt
        assert "endpoint" in prompt.lower()

    def test_spec_type_ui(self):
        """Test UI spec type template."""
        prompt = build_spec_prompt(
            summary="Add button",
            requirements=["Button shows on page"],
            context={},
            spec_type="ui",
        )
        assert "UI" in prompt
        assert "component" in prompt.lower()

    def test_spec_type_backend(self):
        """Test backend spec type template."""
        prompt = build_spec_prompt(
            summary="Add service",
            requirements=["Service handles requests"],
            context={},
            spec_type="backend",
        )
        assert "backend" in prompt.lower() or "BACKEND" in prompt

    def test_spec_type_data(self):
        """Test data spec type template."""
        prompt = build_spec_prompt(
            summary="Add data transform",
            requirements=["Transform input to output"],
            context={},
            spec_type="data",
        )
        assert "data" in prompt.lower() or "DATA" in prompt


class TestParseSpecOutput:
    """Tests for spec output parsing."""

    def test_valid_spec_output(self):
        """Test parsing valid spec output."""
        output = json.dumps(
            {
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
            }
        )
        spec = parse_spec_output(output)
        assert spec["summary"] == "Test feature"
        assert len(spec["requirements"]) == 1
        assert spec["requirements"][0]["id"] == "REQ-001"

    def test_strips_markdown_code_blocks(self):
        """Test that markdown code blocks are stripped."""
        output = """```json
{"summary": "Test", "requirements": [], "technical_notes": [], "file_changes": []}
```"""
        spec = parse_spec_output(output)
        assert spec["summary"] == "Test"

    def test_missing_required_field_raises(self):
        """Test that missing required field raises ValueError."""
        output = json.dumps({"summary": "Test"})
        with pytest.raises(ValueError, match="Missing required field"):
            parse_spec_output(output)

    def test_missing_test_criteria_raises(self):
        """Test that missing test_criteria raises ValueError."""
        output = json.dumps(
            {
                "summary": "Test",
                "requirements": [{"description": "Test"}],
                "technical_notes": [],
                "file_changes": [],
            }
        )
        with pytest.raises(ValueError, match="test_criteria"):
            parse_spec_output(output)

    def test_invalid_json_raises(self):
        """Test that invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="(Invalid JSON|No JSON found)"):
            parse_spec_output("not json at all")


class TestGenerateSpecWithRetry:
    """Tests for spec generation with retry."""

    def test_successful_generation(self):
        """Test successful spec generation on first try."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps(
            {
                "summary": "Test",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "description": "Req",
                        "test_criteria": "Test",
                        "priority": "must",
                    }
                ],
                "technical_notes": [],
                "file_changes": [],
            }
        )

        spec = generate_spec_with_retry(
            mock_llm,
            summary="Test",
            requirements=["Req"],
            context={},
        )

        assert spec["summary"] == "Test"
        assert mock_llm.complete.call_count == 1

    def test_retry_on_parse_error(self):
        """Test retry on parse error."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "not valid json",
            json.dumps(
                {
                    "summary": "Test",
                    "requirements": [
                        {
                            "id": "REQ-001",
                            "description": "Req",
                            "test_criteria": "Test",
                            "priority": "must",
                        }
                    ],
                    "technical_notes": [],
                    "file_changes": [],
                }
            ),
        ]

        spec = generate_spec_with_retry(mock_llm, summary="Test", requirements=["Req"], context={})

        assert spec["summary"] == "Test"
        assert mock_llm.complete.call_count == 2

    def test_max_retries_exceeded(self):
        """Test that max retries raises after failures."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "still not valid"

        with pytest.raises(ValueError, match="failed after 3 attempts"):
            generate_spec_with_retry(mock_llm, summary="Test", requirements=["Req"], context={})


class TestLanguageDetection:
    """Tests for language detection."""

    def test_detect_python(self):
        """Test Python detection."""
        context = {"existing_files": ["main.py", "utils.py"]}
        assert detect_language(context) == "python"

    def test_detect_typescript(self):
        """Test TypeScript detection."""
        context = {"existing_files": ["index.ts", "app.tsx"]}
        assert detect_language(context) == "typescript"

    def test_detect_javascript(self):
        """Test JavaScript detection."""
        context = {"existing_files": ["index.js", "app.jsx"]}
        assert detect_language(context) == "javascript"

    def test_detect_go(self):
        """Test Go detection."""
        context = {"existing_files": ["main.go", "util.go"]}
        assert detect_language(context) == "go"

    def test_default_to_python(self):
        """Test default fallback to Python."""
        context = {"existing_files": []}
        assert detect_language(context) == "python"


class TestBuildCodePrompt:
    """Tests for code prompt building."""

    def test_basic_code_prompt(self):
        """Test basic code prompt generation."""
        spec = {
            "summary": "Test feature",
            "requirements": [],
            "technical_notes": [],
            "file_changes": [{"path": "test.py", "change_type": "create", "description": "Test"}],
        }
        prompt = build_code_prompt(
            spec=spec,
            test_cases=[{"name": "test_one", "input": "x", "expected": "y"}],
            repo_context={"existing_files": []},
        )
        assert "Test feature" in prompt
        assert "test_one" in prompt

    def test_language_standards_included(self):
        """Test that language standards are included in prompt."""
        spec = {"summary": "Test", "requirements": [], "technical_notes": [], "file_changes": []}
        prompt = build_code_prompt(spec, [], {}, language="python")
        assert "PEP 8" in prompt
        assert "type hints" in prompt.lower()

    def test_existing_code_context(self):
        """Test that existing code is included in context."""
        spec = {"summary": "Test", "requirements": [], "technical_notes": [], "file_changes": []}
        repo_context = {
            "existing_files": ["app/utils.py"],
            "file_contents": {"app/utils.py": "def helper(): pass"},
        }
        prompt = build_code_prompt(spec, [], repo_context)
        assert "helper" in prompt or "utils.py" in prompt


class TestParseCodeOutput:
    """Tests for code output parsing."""

    def test_valid_code_output(self):
        """Test parsing valid code output."""
        output = json.dumps(
            {
                "files": [
                    {"path": "test.py", "change_type": "create", "content": "print('hello')"}
                ],
                "decisions": [],
                "test_changes": [],
            }
        )
        result = parse_code_output(output)
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "test.py"

    def test_missing_files_field_raises(self):
        """Test that missing files field raises ValueError."""
        output = json.dumps({"decisions": []})
        with pytest.raises(ValueError, match="files"):
            parse_code_output(output)

    def test_missing_content_raises(self):
        """Test that missing content in file raises ValueError."""
        output = json.dumps(
            {
                "files": [{"path": "test.py", "change_type": "create"}],
                "decisions": [],
            }
        )
        with pytest.raises(ValueError, match="content"):
            parse_code_output(output)


class TestGenerateCodeWithRetry:
    """Tests for code generation with retry."""

    def test_successful_generation(self):
        """Test successful code generation on first try."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps(
            {
                "files": [{"path": "test.py", "change_type": "create", "content": "x=1"}],
                "decisions": [],
                "test_changes": [],
            }
        )

        result = generate_code_with_retry(
            mock_llm,
            spec={"summary": "Test", "requirements": [], "technical_notes": [], "file_changes": []},
            test_cases=[],
            repo_context={},
        )

        assert len(result["files"]) == 1
        assert mock_llm.complete.call_count == 1


class TestLanguageStandards:
    """Tests for language standards."""

    def test_python_standards(self):
        """Test Python standards are defined."""
        assert "python" in LANGUAGE_STANDARDS
        assert "style" in LANGUAGE_STANDARDS["python"]
        assert "typing" in LANGUAGE_STANDARDS["python"]

    def test_typescript_standards(self):
        """Test TypeScript standards are defined."""
        assert "typescript" in LANGUAGE_STANDARDS
        assert LANGUAGE_STANDARDS["typescript"]["style"] == "Strict TypeScript"

    def test_go_standards(self):
        """Test Go standards are defined."""
        assert "go" in LANGUAGE_STANDARDS
        assert "gofmt" in LANGUAGE_STANDARDS["go"]["style"]
