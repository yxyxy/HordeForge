from __future__ import annotations

from agents.fix_agent_v2 import EnhancedFixAgent


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def test_enhanced_fix_agent_no_failures():
    """Test fix agent when no tests are failing."""
    agent = EnhancedFixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "SUCCESS",
            "test_results",
            {"total": 5, "passed": 5, "failed": 0},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["remaining_failures"] == 0
    assert content["fix_iteration"] == 1


def test_enhanced_fix_agent_first_iteration():
    """Test fix agent on first iteration with failures."""
    agent = EnhancedFixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 3, "failed": 2},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["fix_iteration"] == 1
    assert content["remaining_failures"] == 1  # 2 - 1 = 1


def test_enhanced_fix_agent_subsequent_iteration():
    """Test fix agent increments iteration correctly."""
    agent = EnhancedFixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": 2, "remaining_failures": 1},
        ),
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 4, "failed": 1},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["fix_iteration"] == 3  # Previous 2 + 1


def test_enhanced_fix_agent_max_iterations():
    """Test fix agent stops at max iterations."""
    agent = EnhancedFixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": 5, "remaining_failures": 1},
        ),
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 4, "failed": 1},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "FAILED"
    assert "Max iterations" in result["logs"][0]


def test_enhanced_fix_agent_includes_test_fix():
    """Test fix agent modifies test file when needed."""
    agent = EnhancedFixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 3, "passed": 1, "failed": 2},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    paths = [f["path"] for f in content.get("files", [])]
    assert any("test" in p.lower() for p in paths)


def test_enhanced_fix_agent_name():
    """Test agent name."""
    agent = EnhancedFixAgent()
    assert agent.name == "fix_agent"
    assert "fix" in agent.description.lower()


def test_enhanced_fix_agent_iteration_limit_default():
    """Test default max iterations value."""
    agent = EnhancedFixAgent()
    # Default value is 5 (from env var or constant)
    assert agent.MAX_ITERATIONS >= 1


def _get_content(result: dict, artifact_type: str) -> dict:
    """Extract content from agent result."""
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}
