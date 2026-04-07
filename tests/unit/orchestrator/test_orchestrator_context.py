from orchestrator.context import ExecutionContext
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus


def test_execution_context_includes_required_fields():
    context = ExecutionContext(
        run_id="run-1",
        pipeline_name="pipeline-a",
        inputs={"repo_url": "x"},
    )
    assert context.run_id == "run-1"
    assert context.pipeline_name == "pipeline-a"
    assert context.inputs == {"repo_url": "x"}
    assert context.state["repo_url"] == "x"
    assert context.metadata == {}
    assert context.pipeline_state.run_id == "run-1"
    assert context.pipeline_state.pipeline_name == "pipeline-a"
    assert context.pipeline_state.current_step is None
    assert context.pipeline_state.artifacts["repo_url"] == "x"


def test_execution_context_updates_state_and_step_results():
    context = ExecutionContext(run_id="run-2", pipeline_name="pipeline-b")
    context.update_state({"a": 1})
    context.set_state_value("b", 2)
    context.record_step_result("step_1", {"status": "SUCCESS"})

    assert context.state["a"] == 1
    assert context.state["b"] == 2
    assert context.step_results["step_1"]["status"] == "SUCCESS"
    assert context.state["step_1"]["status"] == "SUCCESS"
    assert context.pipeline_state.artifacts["a"] == 1
    assert context.pipeline_state.artifacts["b"] == 2
    assert context.pipeline_state.artifacts["step_1"]["status"] == "SUCCESS"


def test_execution_context_syncs_pipeline_state_from_run_state():
    context = ExecutionContext(run_id="run-3", pipeline_name="pipeline-c")
    run_state = PipelineRunState.from_steps(
        run_id="run-3",
        pipeline_name="pipeline-c",
        steps=[("step_1", "repo_connector"), ("step_2", "rag_initializer")],
    )
    run_state.mark_step_status("step_1", StepStatus.RUNNING, started_at="t1")
    run_state.mark_step_status("step_1", StepStatus.SUCCESS, finished_at="t2")
    run_state.mark_step_status("step_2", StepStatus.RUNNING, started_at="t3")

    context.sync_pipeline_state_from_run_state(run_state)

    assert context.pipeline_state.current_step == "step_2"
    assert context.pipeline_state.pending_steps == ["step_2"]
    assert context.pipeline_state.failed_steps == []
    assert context.pipeline_state.retry_state["step_1"] == 0
