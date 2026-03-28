"""Unit tests for LLM agent integration functionality."""

from unittest.mock import Mock, patch

import pytest

from agents.code_generator import EnhancedCodeGenerator
from agents.review_agent import ReviewAgent
from agents.specification_writer import SpecificationWriter
from agents.test_generator import TestGenerator


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
    return {}


class TestLLMAgentIntegration:
    """Test LLM integration with various agents."""

    def test_specification_writer_with_llm(self):
        """Test specification writer with LLM integration."""
        agent = SpecificationWriter()
        context = {
            "use_llm": True,
            "feature_description": "Implement OAuth2 login",
            "dod": {"acceptance_criteria": ["The feature should work correctly"]},
            "rules": {"version": "1.0", "documents": {}},
        }

        # Mock the LLM wrapper to avoid actual API calls
        with patch("agents.specification_writer.get_llm_wrapper") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.complete.return_value = """
            {
                "summary": "Test feature specification",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "description": "The feature should work correctly",
                        "test_criteria": "Verify feature works as expected",
                        "priority": "must"
                    }
                ],
                "technical_notes": ["Follow existing patterns"],
                "file_changes": [
                    {
                        "path": "src/test_feature.py",
                        "change_type": "create",
                        "description": "New feature implementation"
                    }
                ]
            }
            """
            mock_get_llm.return_value = mock_llm

            result = agent.run(context)

            # Verify the result structure
            assert result["status"] == "SUCCESS"
            spec_payload = _artifact_content(result, "spec")
            assert "summary" in spec_payload

            # Verify LLM was called
            mock_llm.complete.assert_called_once()
            mock_llm.close.assert_called_once()

    def test_code_generator_with_llm(self):
        """Test code generator with LLM integration."""
        agent = EnhancedCodeGenerator()
        context = {
            "use_llm": True,
            "spec": {
                "summary": "Test feature implementation",
                "requirements": ["The feature should work correctly"],
                "file_changes": [
                    {
                        "path": "src/test_feature.py",
                        "change_type": "create",
                        "description": "New feature implementation",
                    }
                ],
            },
            "tests": {"test_cases": []},
        }

        # Mock the LLM wrapper to avoid actual API calls
        with patch("agents.code_generator.get_llm_wrapper") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.complete.return_value = """
            {
                "files": [
                    {
                        "path": "src/test_feature.py",
                        "change_type": "create",
                        "content": "def test_function():\\n    return \"test\""
                    }
                ],
                "decisions": [],
                "test_changes": []
            }
            """
            mock_get_llm.return_value = mock_llm

            result = agent.run(context)

            # Verify the result structure
            assert result["status"] == "SUCCESS"
            patch_payload = _artifact_content(result, "code_patch")
            assert "files" in patch_payload
            assert patch_payload["llm_enhanced"] is True

            # Verify LLM was called
            mock_llm.complete.assert_called_once()
            mock_llm.close.assert_called_once()

    def test_test_generator_with_llm(self):
        """Test test_generator with LLM integration."""
        agent = TestGenerator()
        context = {
            "use_llm": True,
            "spec": {
                "summary": "Test feature implementation",
                "requirements": [{"description": "The feature should work correctly"}],
                "file_changes": [
                    {"path": "src/test_feature.py", "description": "New feature implementation"}
                ],
            },
            "code_patch": {
                "files": [
                    {
                        "path": "src/test_feature.py",
                        "content": 'def test_function():\\n    return "test"',
                    }
                ]
            },
        }

        # Mock the LLM wrapper to avoid actual API calls
        with patch("agents.test_generator.get_llm_wrapper") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.complete.return_value = """
            {
                "test_cases": [
                    {
                        "name": "test_feature_works",
                        "type": "unit",
                        "description": "Test that feature works correctly",
                        "file_path": "tests/test_feature.py",
                        "content": "def test_feature_works():\\n    assert True",
                        "expected_result": "pass"
                    }
                ],
                "coverage_analysis": {
                    "covered_functions": [],
                    "missing_coverage": [],
                    "test_strategy": "LLM generated"
                }
            }
            """
            mock_get_llm.return_value = mock_llm

            result = agent.run(context)

            # Verify the result structure
            assert result["status"] == "SUCCESS"
            tests_payload = _artifact_content(result, "tests")
            assert len(tests_payload["test_cases"]) > 0
            assert tests_payload["llm_enhanced"] is True

            # Verify LLM was called
            mock_llm.complete.assert_called_once()
            mock_llm.close.assert_called_once()

    def test_review_agent_with_llm(self):
        """Test review agent with LLM integration."""
        agent = ReviewAgent()
        context = {
            "use_llm": True,
            "code_patch": {
                "files": [
                    {
                        "path": "src/test_feature.py",
                        "content": 'def test_function():\\n    return "test"',
                        "change_type": "create",
                    }
                ]
            },
        }

        # Mock the LLM wrapper to avoid actual API calls
        with patch("agents.review_agent.get_llm_wrapper") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.complete.return_value = """
            {
                "overall_decision": "approve",
                "summary": "Code looks good",
                "findings": [],
                "strengths": ["Clean implementation"],
                "recommendations": ["Add more tests"],
                "confidence": 0.9
            }
            """
            mock_get_llm.return_value = mock_llm

            result = agent.run(context)

            # Verify the result structure
            assert result["status"] == "SUCCESS"
            review_payload = _artifact_content(result, "review_result")
            assert review_payload["decision"] == "approve"
            assert review_payload["llm_enhanced"] is True

            # Verify LLM was called
            mock_llm.complete.assert_called_once()
            mock_llm.close.assert_called_once()

    def test_agents_fallback_without_llm(self):
        """Test that agents fall back gracefully when LLM is not available."""
        # Test specification writer fallback
        spec_agent = SpecificationWriter()
        context = {
            "use_llm": True,  # Even if LLM is requested
            "feature_description": "Implement feature flag",
            "dod": {"acceptance_criteria": ["The feature should work correctly"]},
        }

        # Mock LLM to return None (not available)
        with patch("agents.specification_writer.get_llm_wrapper") as mock_get_llm:
            mock_get_llm.return_value = None

            result = spec_agent.run(context)

            # Should still succeed with deterministic generation
            assert result["status"] == "SUCCESS"
            spec_payload = _artifact_content(result, "spec")
            assert "schema_version" in spec_payload

        # Test code generator fallback
        code_agent = EnhancedCodeGenerator()
        context = {
            "use_llm": True,  # Even if LLM is requested
            "spec": {
                "summary": "Test feature implementation",
                "requirements": ["The feature should work correctly"],
            },
        }

        with patch("agents.code_generator.get_llm_wrapper") as mock_get_llm:
            mock_get_llm.return_value = None

            result = code_agent.run(context)

            # Should still succeed with deterministic generation
            assert result["status"] == "SUCCESS"
            patch_payload = _artifact_content(result, "code_patch")
            assert patch_payload["llm_enhanced"] is False

    def test_agents_with_llm_disabled(self):
        """Test that agents work when LLM is explicitly disabled."""
        spec_agent = SpecificationWriter()
        context = {
            "use_llm": False,  # LLM explicitly disabled
            "feature_description": "Implement feature flag",
            "dod": {"acceptance_criteria": ["The feature should work correctly"]},
        }

        # Even if LLM is available, it shouldn't be used
        with patch("agents.specification_writer.get_llm_wrapper") as mock_get_llm:
            result = spec_agent.run(context)

            # Should use deterministic generation
            assert result["status"] == "SUCCESS"
            spec_payload = _artifact_content(result, "spec")
            assert "schema_version" in spec_payload
            # LLM should not be called
            mock_get_llm.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])
