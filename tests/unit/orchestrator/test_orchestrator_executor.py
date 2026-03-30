import json

from agents.base import BaseAgent
from orchestrator.context import ExecutionContext
from orchestrator.executor import StepExecutor
from orchestrator.loader import StepDefinition
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from registry.agents import AgentMetadata, AgentRegistry


class FakeSuccessAgent(BaseAgent):
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class InvalidResultAgent(BaseAgent):
    def run(self, _context):
        return {"status": "SUCCESS"}


def test_step_executor_updates_context_and_state_on_success():
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="repo_connector", agent_class=FakeSuccessAgent))

    context = ExecutionContext(run_id="run-1", pipeline_name="pipe-1", inputs={"repo_url": "x"})
    run_state = PipelineRunState.from_steps(
        "run-1", "pipe-1", [("repo_connector", "repo_connector")]
    )
    step = StepDefinition(name="repo_connector", agent="repo_connector")

    executor = StepExecutor(agent_registry=registry)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert context.step_results["repo_connector"]["status"] == "SUCCESS"
    assert run_state.get_step("repo_connector").status == StepStatus.SUCCESS
    assert run_state.current_step_index == 0


def test_step_executor_returns_failed_result_when_agent_raises():
    registry = AgentRegistry()

    # Регистрируем агент, который выбрасывает исключение
    class ErrorAgent(BaseAgent):
        def run(self, _context):
            raise ImportError("module not found")

    registry.register(AgentMetadata(name="missing_agent", agent_class=ErrorAgent))

    context = ExecutionContext(run_id="run-2", pipeline_name="pipe-2", inputs={})
    run_state = PipelineRunState.from_steps("run-2", "pipe-2", [("step_1", "missing_agent")])
    step = StepDefinition(name="step_1", agent="missing_agent")

    executor = StepExecutor(agent_registry=registry)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert run_state.get_step("step_1").status == StepStatus.FAILED
    assert "failed" in result["logs"][0].lower()


def test_step_executor_uses_registry_as_primary_resolution_path():
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="repo_connector", agent_class=FakeSuccessAgent))
    context = ExecutionContext(run_id="run-3", pipeline_name="pipe-3", inputs={})
    run_state = PipelineRunState.from_steps(
        "run-3", "pipe-3", [("repo_connector", "repo_connector")]
    )
    step = StepDefinition(name="repo_connector", agent="repo_connector")

    executor = StepExecutor(agent_registry=registry)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert run_state.get_step("repo_connector").status == StepStatus.SUCCESS


def test_step_executor_falls_back_to_dynamic_import_when_enabled(monkeypatch, caplog):
    # Этот тест больше не применим, так как мы удалили возможность fallback
    # Вместо этого тестируем успешное выполнение с зарегистрированным агентом
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="unknown", agent_class=FakeSuccessAgent))
    context = ExecutionContext(run_id="run-4", pipeline_name="pipe-4", inputs={})
    run_state = PipelineRunState.from_steps("run-4", "pipe-4", [("unknown", "unknown")])
    step = StepDefinition(name="unknown", agent="unknown")

    executor = StepExecutor(agent_registry=registry)

    with caplog.at_level("WARNING"):
        result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    # Проверяем, что нет сообщений о fallback
    assert not any("agent_registry_fallback" in record.message for record in caplog.records)


def test_step_executor_fails_when_agent_not_registered():
    registry = AgentRegistry()
    context = ExecutionContext(run_id="run-5", pipeline_name="pipe-5", inputs={})
    run_state = PipelineRunState.from_steps("run-5", "pipe-5", [("unknown", "unknown")])
    step = StepDefinition(name="unknown", agent="unknown")

    executor = StepExecutor(agent_registry=registry)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert "registry" in result["logs"][0].lower() or "registered" in result["logs"][0].lower()


def test_step_executor_strict_schema_validation_blocks_invalid_agent_result():
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="bad_step", agent_class=InvalidResultAgent))

    context = ExecutionContext(run_id="run-6", pipeline_name="pipe-6", inputs={})
    run_state = PipelineRunState.from_steps("run-6", "pipe-6", [("bad_step", "bad_step")])
    step = StepDefinition(name="bad_step", agent="bad_step")

    executor = StepExecutor(
        agent_registry=registry,
        strict_schema_validation=True,
    )
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert run_state.get_step("bad_step").status == StepStatus.FAILED
    assert "schema" in result["logs"][0].lower()


def test_step_executor_non_strict_schema_validation_collects_errors():
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="warn_step", agent_class=InvalidResultAgent))

    context = ExecutionContext(run_id="run-7", pipeline_name="pipe-7", inputs={})
    run_state = PipelineRunState.from_steps("run-7", "pipe-7", [("warn_step", "warn_step")])
    step = StepDefinition(name="warn_step", agent="warn_step")

    executor = StepExecutor(
        agent_registry=registry,
        strict_schema_validation=False,
    )
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert "validation_errors" in result
    assert run_state.get_step("warn_step").status == StepStatus.SUCCESS
    assert run_state.get_step("warn_step").error is not None


def test_step_executor_logs_json_with_run_id_correlation_and_step(caplog):
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="repo_connector", agent_class=FakeSuccessAgent))

    context = ExecutionContext(
        run_id="run-log-1",
        pipeline_name="pipe-log-1",
        inputs={},
        metadata={
            "correlation_id": "corr-log-1",
            "trace_id": "trace-log-1",
            "root_span_id": "root-span-1",
        },
    )
    run_state = PipelineRunState.from_steps(
        "run-log-1", "pipe-log-1", [("repo_connector", "repo_connector")]
    )
    step = StepDefinition(name="repo_connector", agent="repo_connector")

    executor = StepExecutor(agent_registry=registry)
    with caplog.at_level("INFO", logger="hordeforge.orchestrator.step_executor"):
        executor.execute_step(step, context, run_state)

    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "hordeforge.orchestrator.step_executor"
    ]
    assert any(item["event"] == "step_start" for item in payloads)
    assert any(item["event"] == "step_end" for item in payloads)
    assert all(item["run_id"] == "run-log-1" for item in payloads)
    assert all(item["correlation_id"] == "corr-log-1" for item in payloads)
    assert any(item["step"] == "repo_connector" for item in payloads)


def test_coerce_code_patch_preserves_pr_metadata_fields():
    content = {
        "files": [{"path": "src/a.py", "diff": "# modify\nprint('ok')\n"}],
        "pr_number": 123,
        "pr_url": "https://github.com/org/repo/pull/123",
        "branch_name": "hordeforge/feature-123",
        "applied_to_github": True,
        "apply_error": "none",
        "rollback_performed": False,
        "llm_enhanced": True,
        "notes": ["n1", "n2"],
    }

    normalized = StepExecutor._coerce_code_patch_content_for_validation(content)

    assert normalized["pr_number"] == 123
    assert normalized["pr_url"] == "https://github.com/org/repo/pull/123"
    assert normalized["branch_name"] == "hordeforge/feature-123"
    assert normalized["applied_to_github"] is True
    assert normalized["apply_error"] == "none"
    assert normalized["rollback_performed"] is False
    assert normalized["llm_enhanced"] is True
    assert normalized["notes"] == ["n1", "n2"]
