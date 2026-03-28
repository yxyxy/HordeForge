from __future__ import annotations

from agents.code_generator import EnhancedCodeGenerator
from agents.specification_writer import EnhancedSpecificationWriter


def _get_content(result: dict, artifact_type: str) -> dict:
    """Extract content from agent result."""
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}


def test_enhanced_specification_writer_basic():
    """Test enhanced spec writer with basic context."""
    writer = EnhancedSpecificationWriter()
    context = {
        "use_llm": False,  # Skip LLM to test deterministic path
        "feature_description": "Implement OAuth2 login flow",
    }
    result = writer.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "spec")
    assert "schema_version" in content
    assert "acceptance_criteria" in content
    assert "technical_specification" in content


def test_enhanced_specification_writer_with_dod():
    """Test spec writer with DoD artifact."""
    writer = EnhancedSpecificationWriter()
    context = {
        "use_llm": False,
        "dod_extractor": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "dod",
                    "content": {
                        "acceptance_criteria": ["Implement OAuth2 login", "Add session management"],
                    },
                }
            ],
        },
    }
    result = writer.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "spec")
    assert len(content["acceptance_criteria"]) >= 1


def test_enhanced_code_generator_basic():
    """Test enhanced code generator with basic context."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert "schema_version" in content
    assert "files" in content
    assert content["llm_enhanced"] is False


def test_enhanced_code_generator_with_spec():
    """Test code generator with spec artifact."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "specification_writer": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "spec",
                    "content": {
                        "summary": "API feature",
                        "file_changes": [
                            {
                                "path": "src/api.py",
                                "change_type": "create",
                                "description": "API module",
                            }
                        ],
                    },
                }
            ],
        },
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert len(content["files"]) > 0


def test_enhanced_code_generator_with_test_cases():
    """Test code generator includes test file when test cases exist."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "test_generator": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "tests",
                    "content": {
                        "test_cases": [
                            {"name": "test_success", "input": "x", "expected": "y"},
                            {"name": "test_failure", "input": "z", "expected": "w"},
                        ]
                    },
                }
            ],
        },
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    # Should have feature file + test file
    paths = [f["path"] for f in content["files"]]
    assert any("test" in p.lower() for p in paths)


def test_enhanced_spec_name():
    """Test agent name and description."""
    writer = EnhancedSpecificationWriter()
    assert writer.name == "specification_writer"
    assert "spec" in writer.description.lower()


def test_enhanced_code_generator_name():
    """Test agent name and description."""
    generator = EnhancedCodeGenerator()
    assert generator.name == "code_generator"
    assert "code" in generator.description.lower()
