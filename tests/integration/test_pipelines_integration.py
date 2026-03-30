from __future__ import annotations

from typing import Any

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor
from registry.agents import AgentRegistry, register_agents
from registry.runtime_adapter import RuntimeRegistryAdapter


def _artifact_content(result: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
    raise AssertionError(f"Artifact '{artifact_type}' is missing.")


def _runtime_registry() -> RuntimeRegistryAdapter:
    registry = AgentRegistry()
    register_agents(registry)
    return RuntimeRegistryAdapter(registry)


class InvalidSchemaAgent:
    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCESS"}


def test_init_pipeline_integration_runs_all_steps_and_returns_summary():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "init_pipeline",
        {
            "repo_url": "https://github.com/yxyxy/hordeforge.git",
            "github_token": "secret",
            "mock_mode": True,
        },
        run_id="it-init-pipeline",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert set(result["steps"].keys()) == {
        "repo_connector",
        "rag_initializer",
        "memory_agent",
        "architecture_evaluator",
        "test_analyzer",
        "pipeline_initializer",
    }
    metadata = _artifact_content(result["steps"]["repo_connector"], "repository_metadata")
    assert metadata["mock_mode"] is True
    assert result["summary"]["step_count"] == 6
    assert result["summary"]["step_results_count"] == 6
    assert result["summary"]["run_status"] == result["status"]


def test_feature_pipeline_integration_happy_path_runs_fix_loop_to_green():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "feature_pipeline",
        {"issue": {"body": "Implement endpoint and tests"}},
        run_id="it-feature-happy",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["code_generator"]["status"] == "SUCCESS"
    assert result["steps"]["test_runner"]["status"] == "SUCCESS"
    assert result["steps"]["fix_agent"]["status"] in {"SUCCESS", "SKIPPED"}
    assert result["steps"]["pr_merge_agent"]["status"] in {"PARTIAL_SUCCESS", "SUCCESS"}


def test_feature_pipeline_integration_validation_failure_stops_execution():
    runtime_registry = _runtime_registry()

    class PartialOverrideRegistry:
        def __init__(self, base_registry: RuntimeRegistryAdapter):
            self._base = base_registry

        def has(self, agent_name: str) -> bool:
            return self._base.has(agent_name)

        def create(self, agent_name: str) -> Any:
            if agent_name == "code_generator":
                return InvalidSchemaAgent()
            return self._base.create(agent_name)

        def get(self, agent_name: str):
            return self._base.get(agent_name)

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(
            agent_registry=PartialOverrideRegistry(runtime_registry),
            strict_schema_validation=True,
        ),
    )
    result = engine.run(
        "feature_pipeline",
        {"issue": {"body": "Force schema validation failure branch"}},
        run_id="it-feature-validation-failure",
    )

    assert result["status"] in {"FAILED", "BLOCKED"}
    assert result["steps"]["code_generator"]["status"] == "FAILED"
    assert "schema" in result["steps"]["code_generator"]["logs"][0].lower()
    assert "test_runner" not in result["steps"]


def test_ci_fix_pipeline_integration_full_flow_from_ci_failure_event():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "ci_fix_pipeline",
        {
            "mock_mode": True,
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {
                "status": "failed",
                "failed_jobs": [{"name": "unit-tests", "reason": "assertion failure"}],
            },
        },
        run_id="it-ci-fix-happy",
    )

    assert result["status"] == "SUCCESS"
    analysis = _artifact_content(result["steps"]["ci_failure_analyzer"], "failure_analysis")
    assert analysis["failed_jobs_count"] == 1
    assert analysis["classification"] in {
        "test_failure",
        "build_failure",
        "infrastructure",
        "unknown",
    }
    ci_issue = _artifact_content(result["steps"]["ci_incident_handoff"], "ci_issue")
    assert ci_issue["created"] is True
    assert ci_issue["mock"] is True
    assert "agent:opened" in ci_issue["labels"]


def test_ci_fix_pipeline_integration_skips_handoff_when_ci_not_failed():
    runtime_registry = _runtime_registry()

    class PartialOverrideRegistry:
        def __init__(self, base_registry: RuntimeRegistryAdapter):
            self._base = base_registry

        def has(self, agent_name: str) -> bool:
            return self._base.has(agent_name)

        def create(self, agent_name: str) -> Any:
            if agent_name == "ci_incident_handoff":
                raise AssertionError("ci_incident_handoff must be skipped by condition")
            return self._base.create(agent_name)

        def get(self, agent_name: str):
            return self._base.get(agent_name)

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_registry=PartialOverrideRegistry(runtime_registry)),
    )
    result = engine.run(
        "ci_fix_pipeline",
        {
            "mock_mode": True,
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"status": "completed", "conclusion": "success"},
        },
        run_id="it-ci-fix-skip-handoff",
    )

    assert result["status"] == "SUCCESS"
    assert result["steps"]["ci_incident_handoff"]["status"] == "SKIPPED"
