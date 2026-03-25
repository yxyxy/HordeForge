from __future__ import annotations

from agents.fix_agent import FixAgent


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def _get_content(result: dict, artifact_type: str) -> dict:
    """Extract content from agent result."""
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}


def test_fix_agent_no_failures():
    """Test fix agent when no tests are failing."""
    agent = FixAgent()
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


def test_fix_agent_first_iteration():
    """Test fix agent on first iteration with failures."""
    agent = FixAgent()
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


def test_fix_agent_subsequent_iteration():
    """Test fix agent increments iteration correctly."""
    agent = FixAgent()
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


def test_fix_agent_iteration_from_string():
    """Test fix agent handles string iteration value from previous patch."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": "5", "remaining_failures": 1},
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
    assert content["fix_iteration"] == 6


def test_fix_agent_produces_patch_files():
    """Test fix agent always emits at least one file change for failures."""
    agent = FixAgent()
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
    assert "src/feature_impl.py" in paths


def test_fix_agent_name():
    """Test agent name."""
    agent = FixAgent()
    assert agent.name == "fix_agent"
    assert "fix" in agent.description.lower()


def test_fix_agent_static_helpers_exist():
    """Test static helper methods remain available."""
    assert callable(FixAgent.parse_stacktrace)
    assert callable(FixAgent.detect_failure)
    assert callable(FixAgent.generate_fix)
