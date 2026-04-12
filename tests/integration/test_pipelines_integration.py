from __future__ import annotations

import os
from typing import Any

import pytest

from agents.context_utils import build_agent_result
from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor
from registry.agents import AgentRegistry, register_agents
from registry.runtime_adapter import RuntimeRegistryAdapter

pytestmark = pytest.mark.usefixtures("stub_llm_for_pipeline_runtime")


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


class _StaticAgent:
    def __init__(
        self,
        *,
        artifact_type: str,
        artifact_content: dict[str, Any],
        status: str = "SUCCESS",
        reason: str = "static integration stub",
    ) -> None:
        self._artifact_type = artifact_type
        self._artifact_content = artifact_content
        self._status = status
        self._reason = reason

    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        return build_agent_result(
            status=self._status,
            artifact_type=self._artifact_type,
            artifact_content=self._artifact_content,
            reason=self._reason,
            confidence=0.99,
            logs=["integration fast stub"],
            next_actions=[],
        )


class _SequenceTestRunnerAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            payload = {
                "framework": "pytest",
                "exit_code": 1,
                "failed": 1,
                "passed": 0,
                "total": 1,
                "result_type": "test_failures",
                "execution_mode": "mock",
            }
            status = "PARTIAL_SUCCESS"
        else:
            payload = {
                "framework": "pytest",
                "exit_code": 0,
                "failed": 0,
                "passed": 1,
                "total": 1,
                "result_type": "passed",
                "execution_mode": "mock",
            }
            status = "SUCCESS"

        result = build_agent_result(
            status=status,
            artifact_type="test_results",
            artifact_content=payload,
            reason="sequence test runner stub",
            confidence=0.99,
            logs=[f"test_runner_calls={self.calls}"],
            next_actions=[],
        )
        result["test_results"] = payload
        return result


class _CountingFixAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content={
                "files": [
                    {
                        "path": "src/feature_impl.py",
                        "change_type": "modify",
                        "content": "def process():\n    return True\n",
                    }
                ],
                "remaining_failures": 0,
            },
            reason="fix agent stub",
            confidence=0.99,
            logs=[f"fix_agent_calls={self.calls}"],
            next_actions=[],
        )


class _CiFixGreenTestRunnerAgent:
    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "framework": "pytest",
            "exit_code": 0,
            "failed": 0,
            "passed": 1,
            "total": 1,
            "result_type": "passed",
            "execution_mode": "real",
            "env_doctor": {
                "missing_required_secrets": ["SECRET_TOKEN"],
                "ready": False,
            },
        }
        result = build_agent_result(
            status="SUCCESS",
            artifact_type="test_results",
            artifact_content=payload,
            reason="ci_fix green test runner",
            confidence=0.99,
            logs=["tests green despite missing optional secrets"],
            next_actions=["review_agent"],
        )
        result["test_results"] = payload
        return result


class _CiFixEnvFailureTestRunnerAgent:
    def run(self, _context: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "framework": "pytest",
            "exit_code": -1,
            "failed": 0,
            "passed": 0,
            "total": 0,
            "result_type": "dependency_error",
            "error_classification": "dependency_error",
            "stderr": "missing required secret SECRET_TOKEN",
            "execution_mode": "real",
            "env_doctor": {
                "missing_required_secrets": ["SECRET_TOKEN"],
                "ready": False,
            },
        }
        result = build_agent_result(
            status="BLOCKED",
            artifact_type="test_results",
            artifact_content=payload,
            reason="environment secrets missing for test execution",
            confidence=0.99,
            logs=["env_doctor_blocked=true", "missing_required_secrets=['SECRET_TOKEN']"],
            next_actions=["provide_env_secrets"],
        )
        result["test_results"] = payload
        return result


class _OverrideRegistry:
    def __init__(
        self,
        base_registry: RuntimeRegistryAdapter,
        overrides: dict[str, Any],
    ) -> None:
        self._base = base_registry
        self._overrides = overrides

    def has(self, agent_name: str) -> bool:
        return agent_name in self._overrides or self._base.has(agent_name)

    def create(self, agent_name: str) -> Any:
        if agent_name in self._overrides:
            return self._overrides[agent_name]
        return self._base.create(agent_name)

    def get(self, agent_name: str):
        return self._base.get(agent_name)


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


def test_feature_pipeline_integration_happy_path_runs_fix_loop_to_green_fast():
    runtime_registry = _runtime_registry()
    test_runner = _SequenceTestRunnerAgent()
    fix_agent = _CountingFixAgent()

    overrides = {
        "rag_initializer": _StaticAgent(
            artifact_type="rag_index",
            artifact_content={"mock": True, "sources": []},
        ),
        "memory_agent": _StaticAgent(
            artifact_type="memory_context",
            artifact_content={"matches": []},
        ),
        "code_generator": _StaticAgent(
            artifact_type="code_patch",
            artifact_content={
                "files": [
                    {
                        "path": "src/feature_impl.py",
                        "change_type": "modify",
                        "content": "def process():\n    return False\n",
                    }
                ],
                "expected_failures": 1,
            },
        ),
        "test_runner": test_runner,
        "fix_agent": fix_agent,
        "review_agent": _StaticAgent(
            artifact_type="review_result",
            artifact_content={"decision": "approve", "findings": []},
        ),
        "pr_merge_agent": _StaticAgent(
            artifact_type="merge_status",
            artifact_content={
                "merged": False,
                "dry_run": True,
                "reason": "approved_by_review_and_tests",
            },
            status="PARTIAL_SUCCESS",
        ),
    }

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_registry=_OverrideRegistry(runtime_registry, overrides)),
    )
    result = engine.run(
        "feature_pipeline",
        {"issue": {"body": "Implement endpoint and tests"}},
        run_id="it-feature-happy-fast",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["code_generator"]["status"] == "SUCCESS"
    assert result["steps"]["test_runner"]["status"] == "SUCCESS"
    assert result["steps"]["fix_agent"]["status"] == "SUCCESS"
    assert test_runner.calls >= 2
    assert fix_agent.calls >= 1
    assert result["steps"]["pr_merge_agent"]["status"] in {"PARTIAL_SUCCESS", "SUCCESS"}


def test_ci_fix_pipeline_integration_executes_review_and_merge_on_green_tests_fast():
    runtime_registry = _runtime_registry()
    overrides = {
        "rag_initializer": _StaticAgent(
            artifact_type="rag_index",
            artifact_content={"mock": True, "sources": []},
        ),
        "memory_agent": _StaticAgent(
            artifact_type="memory_context",
            artifact_content={"matches": []},
        ),
        "ci_failure_analyzer": _StaticAgent(
            artifact_type="failure_analysis",
            artifact_content={
                "classification": "test_failure",
                "candidate_files": ["tests/unit/orchestrator/test_orchestrator_engine.py"],
            },
        ),
        "specification_writer": _StaticAgent(
            artifact_type="spec",
            artifact_content={"schema_version": "1.0", "summary": "Fix CI", "requirements": ["r1"]},
        ),
        "task_decomposer": _StaticAgent(
            artifact_type="subtasks",
            artifact_content={"schema_version": "1.0", "items": [{"id": "t1"}]},
        ),
        "bdd_generator": _StaticAgent(
            artifact_type="bdd_specification",
            artifact_content={"schema_version": "1.0", "gherkin_feature": "Feature: CI fix"},
        ),
        "code_generator": _StaticAgent(
            artifact_type="code_patch",
            artifact_content={
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "orchestrator/executor.py",
                        "change_type": "modify",
                        "content": "def noop() -> None:\n    pass\n",
                    }
                ],
                "pr_number": 77,
                "pr_url": "https://github.com/acme/hordeforge/pull/77",
            },
        ),
        "patch_apply_agent": _StaticAgent(
            artifact_type="prepared_workspace",
            artifact_content={
                "workspace_path": ".",
                "source_path": ".",
                "workspace_mode": "isolated",
                "ready": True,
                "cleanup_required": False,
                "applied_files": 1,
                "checkpoint": {"strategy": "disposable_workspace"},
            },
        ),
        "test_runner": _CiFixGreenTestRunnerAgent(),
        "review_agent": _StaticAgent(
            artifact_type="review_result",
            artifact_content={"decision": "approve", "findings": []},
        ),
        "pr_merge_agent": _StaticAgent(
            artifact_type="merge_status",
            artifact_content={"merged": False, "dry_run": True, "reason": "gates_passed"},
            status="PARTIAL_SUCCESS",
        ),
    }
    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_registry=_OverrideRegistry(runtime_registry, overrides)),
    )
    result = engine.run(
        "ci_fix_pipeline",
        {
            "issue": {"title": "ci incident", "body": "fix ci"},
            "repository": {"full_name": "acme/hf"},
        },
        run_id="it-ci-fix-green-fast",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["test_runner"]["status"] == "SUCCESS"
    assert result["steps"]["review_agent"]["status"] == "SUCCESS"
    assert result["steps"]["pr_merge_agent"]["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["summary"]["pr_reached"] is True


def test_ci_fix_pipeline_integration_skips_merge_when_tests_fail_due_to_missing_secret_fast():
    runtime_registry = _runtime_registry()
    overrides = {
        "rag_initializer": _StaticAgent(
            artifact_type="rag_index",
            artifact_content={"mock": True, "sources": []},
        ),
        "memory_agent": _StaticAgent(
            artifact_type="memory_context",
            artifact_content={"matches": []},
        ),
        "ci_failure_analyzer": _StaticAgent(
            artifact_type="failure_analysis",
            artifact_content={"classification": "test_failure"},
        ),
        "specification_writer": _StaticAgent(
            artifact_type="spec",
            artifact_content={"schema_version": "1.0", "summary": "Fix CI", "requirements": ["r1"]},
        ),
        "task_decomposer": _StaticAgent(
            artifact_type="subtasks",
            artifact_content={"schema_version": "1.0", "items": [{"id": "t1"}]},
        ),
        "bdd_generator": _StaticAgent(
            artifact_type="bdd_specification",
            artifact_content={"schema_version": "1.0", "gherkin_feature": "Feature: CI fix"},
        ),
        "code_generator": _StaticAgent(
            artifact_type="code_patch",
            artifact_content={
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "orchestrator/executor.py",
                        "change_type": "modify",
                        "content": "def noop() -> None:\n    pass\n",
                    }
                ],
            },
        ),
        "patch_apply_agent": _StaticAgent(
            artifact_type="prepared_workspace",
            artifact_content={
                "workspace_path": ".",
                "source_path": ".",
                "workspace_mode": "isolated",
                "ready": True,
                "cleanup_required": False,
                "applied_files": 1,
                "checkpoint": {"strategy": "disposable_workspace"},
            },
        ),
        "test_runner": _CiFixEnvFailureTestRunnerAgent(),
        "fix_agent": _CountingFixAgent(),
        "review_agent": _StaticAgent(
            artifact_type="review_result",
            artifact_content={"decision": "approve", "findings": []},
        ),
        "pr_merge_agent": _StaticAgent(
            artifact_type="merge_status",
            artifact_content={"merged": False, "dry_run": True, "reason": "must_be_skipped"},
            status="PARTIAL_SUCCESS",
        ),
    }
    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        max_loop_iterations=1,
        step_executor=StepExecutor(agent_registry=_OverrideRegistry(runtime_registry, overrides)),
    )
    result = engine.run(
        "ci_fix_pipeline",
        {
            "issue": {"title": "ci incident", "body": "fix ci"},
            "repository": {"full_name": "acme/hf"},
        },
        run_id="it-ci-fix-env-failure-fast",
    )

    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["steps"]["test_runner"]["status"] == "BLOCKED"
    assert result["steps"]["review_agent"]["status"] == "SKIPPED"
    assert result["steps"]["pr_merge_agent"]["status"] == "SKIPPED"
    assert result["summary"]["blocked_by"] == "env_missing_secrets"
    assert result["summary"]["pr_reached"] is False


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


@pytest.mark.slow
@pytest.mark.skipif(
    os.getenv("HF_RUN_SLOW_INTEGRATION", "0") != "1",
    reason="Set HF_RUN_SLOW_INTEGRATION=1 to run slow real happy-path integration test.",
)
def test_feature_pipeline_integration_happy_path_runs_fix_loop_to_green_real():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "feature_pipeline",
        {"issue": {"body": "Implement endpoint and tests"}},
        run_id="it-feature-happy-real",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["code_generator"]["status"] == "SUCCESS"
    assert result["steps"]["test_runner"]["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "BLOCKED"}
    if "fix_agent" in result["steps"]:
        assert result["steps"]["fix_agent"]["status"] in {"SUCCESS", "SKIPPED"}
    assert result["steps"]["pr_merge_agent"]["status"] in {"PARTIAL_SUCCESS", "SUCCESS"}


def test_ci_scanner_pipeline_integration_full_flow_from_ci_failure_event():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "ci_scanner_pipeline",
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


def test_ci_scanner_pipeline_integration_skips_handoff_when_ci_not_failed():
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
        "ci_scanner_pipeline",
        {
            "mock_mode": True,
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"status": "completed", "conclusion": "success"},
        },
        run_id="it-ci-fix-skip-handoff",
    )

    assert result["status"] == "SUCCESS"
    assert result["steps"]["ci_incident_handoff"]["status"] == "SKIPPED"
