import json

from agents.registry import AgentRegistry
from orchestrator.context import ExecutionContext
from orchestrator.executor import StepExecutor
from orchestrator.loader import StepDefinition
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus


class FakeSuccessAgent:
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class InvalidResultAgent:
    def run(self, _context):
        return {"status": "SUCCESS"}


def test_step_executor_updates_context_and_state_on_success():
    context = ExecutionContext(run_id="run-1", pipeline_name="pipe-1", inputs={"repo_url": "x"})
    run_state = PipelineRunState.from_steps(
        "run-1", "pipe-1", [("repo_connector", "repo_connector")]
    )
    step = StepDefinition(name="repo_connector", agent="repo_connector")

    executor = StepExecutor(agent_factory=lambda _: FakeSuccessAgent())
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert context.step_results["repo_connector"]["status"] == "SUCCESS"
    assert run_state.get_step("repo_connector").status == StepStatus.SUCCESS
    assert run_state.current_step_index == 0


def test_step_executor_returns_failed_result_when_agent_raises():
    context = ExecutionContext(run_id="run-2", pipeline_name="pipe-2", inputs={})
    run_state = PipelineRunState.from_steps("run-2", "pipe-2", [("step_1", "missing_agent")])
    step = StepDefinition(name="step_1", agent="missing_agent")

    def _raise(_agent_name: str):
        raise ImportError("module not found")

    executor = StepExecutor(agent_factory=_raise)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert run_state.get_step("step_1").status == StepStatus.FAILED
    assert "failed" in result["logs"][0].lower()


def test_step_executor_uses_registry_as_primary_resolution_path():
    registry = AgentRegistry()
    registry.register("repo_connector", FakeSuccessAgent)
    context = ExecutionContext(run_id="run-3", pipeline_name="pipe-3", inputs={})
    run_state = PipelineRunState.from_steps(
        "run-3", "pipe-3", [("repo_connector", "repo_connector")]
    )
    step = StepDefinition(name="repo_connector", agent="repo_connector")

    executor = StepExecutor(agent_registry=registry, enable_dynamic_fallback=False)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert run_state.get_step("repo_connector").status == StepStatus.SUCCESS


def test_step_executor_falls_back_to_dynamic_import_when_enabled(monkeypatch, caplog):
    registry = AgentRegistry()
    context = ExecutionContext(run_id="run-4", pipeline_name="pipe-4", inputs={})
    run_state = PipelineRunState.from_steps("run-4", "pipe-4", [("unknown", "unknown")])
    step = StepDefinition(name="unknown", agent="unknown")

    executor = StepExecutor(agent_registry=registry, enable_dynamic_fallback=True)
    monkeypatch.setattr(executor, "_dynamic_import_agent", lambda _: FakeSuccessAgent())

    with caplog.at_level("WARNING"):
        result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert any("agent_registry_fallback" in record.message for record in caplog.records)


def test_step_executor_fails_when_fallback_disabled_and_agent_absent():
    registry = AgentRegistry()
    context = ExecutionContext(run_id="run-5", pipeline_name="pipe-5", inputs={})
    run_state = PipelineRunState.from_steps("run-5", "pipe-5", [("unknown", "unknown")])
    step = StepDefinition(name="unknown", agent="unknown")

    executor = StepExecutor(agent_registry=registry, enable_dynamic_fallback=False)
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert "registry" in result["logs"][0].lower()


def test_step_executor_strict_schema_validation_blocks_invalid_agent_result():
    context = ExecutionContext(run_id="run-6", pipeline_name="pipe-6", inputs={})
    run_state = PipelineRunState.from_steps("run-6", "pipe-6", [("bad_step", "bad_step")])
    step = StepDefinition(name="bad_step", agent="bad_step")

    executor = StepExecutor(
        agent_factory=lambda _: InvalidResultAgent(),
        strict_schema_validation=True,
    )
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "FAILED"
    assert run_state.get_step("bad_step").status == StepStatus.FAILED
    assert "schema" in result["logs"][0].lower()


def test_step_executor_non_strict_schema_validation_collects_errors():
    context = ExecutionContext(run_id="run-7", pipeline_name="pipe-7", inputs={})
    run_state = PipelineRunState.from_steps("run-7", "pipe-7", [("warn_step", "warn_step")])
    step = StepDefinition(name="warn_step", agent="warn_step")

    executor = StepExecutor(
        agent_factory=lambda _: InvalidResultAgent(),
        strict_schema_validation=False,
    )
    result = executor.execute_step(step, context, run_state)

    assert result["status"] == "SUCCESS"
    assert "validation_errors" in result
    assert run_state.get_step("warn_step").status == StepStatus.SUCCESS
    assert run_state.get_step("warn_step").error is not None


def test_step_executor_logs_json_with_run_id_correlation_and_step(caplog):
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

    executor = StepExecutor(agent_factory=lambda _: FakeSuccessAgent())
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
