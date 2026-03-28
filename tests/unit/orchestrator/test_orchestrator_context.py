from orchestrator.context import ExecutionContext


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


def test_execution_context_updates_state_and_step_results():
    context = ExecutionContext(run_id="run-2", pipeline_name="pipeline-b")
    context.update_state({"a": 1})
    context.set_state_value("b", 2)
    context.record_step_result("step_1", {"status": "SUCCESS"})

    assert context.state["a"] == 1
    assert context.state["b"] == 2
    assert context.step_results["step_1"]["status"] == "SUCCESS"
    assert context.state["step_1"]["status"] == "SUCCESS"
