from agents.code_generator import CodeGenerator
from agents.fix_agent import FixAgent
from agents.specification_writer import SpecificationWriter
from agents.task_decomposer import TaskDecomposer
from agents.test_generator import TestGenerator
from agents.test_runner import TestRunner


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    raise AssertionError(f"Artifact not found: {artifact_type}")


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def _rules_payload(version: str = "1.0") -> dict:
    return {
        "version": version,
        "documents": {
            "coding": {"source_path": "rules/coding_rules.md", "content": "coding"},
            "testing": {"source_path": "rules/testing_rules.md", "content": "testing"},
            "security": {"source_path": "rules/security_rules.md", "content": "security"},
        },
        "sources": [
            "rules/coding_rules.md",
            "rules/testing_rules.md",
            "rules/security_rules.md",
        ],
        "combined": "rules content",
        "checksum": "checksum",
    }


def test_specification_writer_builds_spec_from_dod():
    agent = SpecificationWriter()
    context = {
        "dod_extractor": _step_result(
            "SUCCESS",
            "dod",
            {
                "schema_version": "1.0",
                "acceptance_criteria": ["Add API endpoint", "Add tests"],
                "bdd_scenarios": [],
            },
        ),
        "rules": _rules_payload(),
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    spec = _artifact_content(result, "spec")
    assert spec["schema_version"] == "1.0"
    assert spec["requirements"]
    assert any("rules/security_rules.md" in item for item in spec["requirements"])
    assert any(item == "rules_version=1.0" for item in spec["notes"])


def test_task_decomposer_returns_prioritized_subtasks():
    agent = TaskDecomposer()
    context = {
        "issue": {
            "title": "Implement login feature",
            "body": "Add API endpoint and UI for authentication",
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    subtasks = (
        _artifact_content(result, "subtasks")
        if "subtasks" in result.get("artifact_type", "")
        else _artifact_content(result, "task_decomposition")
    )
    assert subtasks.get("items") or subtasks.get("subtasks")
    items = subtasks.get("items", [])
    if items:
        assert all("priority" in item and "estimate_hours" in item for item in items)


def test_test_generator_returns_schema_ready_tests_artifact():
    agent = TestGenerator()
    context = {
        "task_decomposer": _step_result(
            "SUCCESS",
            "subtasks",
            {
                "items": [
                    {"id": "T1", "title": "Implement login", "priority": "P0", "estimate_hours": 4}
                ]
            },
        ),
        "specification_writer": _step_result(
            "SUCCESS",
            "spec",
            {
                "schema_version": "1.0",
                "summary": "Auth feature",
                "feature_description": "Add login",
                "acceptance_criteria": ["User can log in"],
            },
        ),
        "rules": _rules_payload(),
    }

    result = agent.run(context)

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    tests = _artifact_content(result, "tests")
    assert tests["schema_version"] == "2.1"
    assert tests["test_cases"]


def test_code_generator_returns_dry_run_patch_with_decisions():
    agent = CodeGenerator()
    context = {
        "task_decomposer": _step_result(
            "SUCCESS",
            "subtasks",
            {
                "items": [
                    {"id": "T1", "title": "Implement login", "priority": "P0", "estimate_hours": 4}
                ]
            },
        ),
        "test_generator": _step_result(
            "SUCCESS",
            "tests",
            {
                "schema_version": "1.0",
                "test_cases": [{"name": "test_login", "type": "unit", "expected_result": "pass"}],
            },
        ),
        "rules": _rules_payload(),
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    patch = _artifact_content(result, "code_patch")
    assert patch["schema_version"] == "2.0"
    assert patch["files"]
    assert patch["dry_run"] is False
    assert any(item == "rules_version=1.0" for item in patch["decisions"])


def test_test_runner_returns_structured_mock_test_results():
    agent = TestRunner()
    context = {
        "code_generator": _step_result(
            "SUCCESS",
            "code_patch",
            {
                "schema_version": "1.0",
                "files": [{"path": "src/app.py", "diff": "+print('x')"}],
                "expected_failures": 1,
            },
        )
    }

    result = agent.run(context)

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["test_results"]["failed"] == 1
    structured = _artifact_content(result, "test_results")
    assert structured["total"] >= structured["failed"]


def test_fix_agent_generates_new_patch_and_reduces_failures():
    agent = FixAgent()
    context = {
        "test_runner": {
            "status": "PARTIAL_SUCCESS",
            "test_results": {"total": 4, "failed": 2, "passed": 2},
            "artifacts": [
                {"type": "test_results", "content": {"total": 4, "failed": 2, "passed": 2}}
            ],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        },
        "code_generator": _step_result(
            "SUCCESS",
            "code_patch",
            {
                "schema_version": "1.0",
                "files": [{"path": "src/app.py", "diff": "+print('x')"}],
                "expected_failures": 2,
            },
        ),
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    patch = _artifact_content(result, "code_patch")
    assert patch["schema_version"] == "1.0"
    assert patch["remaining_failures"] == 1
    assert patch["fix_iteration"] >= 1
