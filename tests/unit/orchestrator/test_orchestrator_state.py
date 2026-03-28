from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus


def test_pipeline_run_state_tracks_steps_and_index():
    run_state = PipelineRunState.from_steps(
        run_id="run-1",
        pipeline_name="pipe-1",
        steps=[("step_1", "repo_connector"), ("step_2", "rag_initializer")],
    )

    assert len(run_state.steps) == 2
    assert run_state.current_step_index == 0
    run_state.advance_index()
    assert run_state.current_step_index == 1


def test_pipeline_run_state_serialization_roundtrip():
    run_state = PipelineRunState.from_steps(
        run_id="run-2",
        pipeline_name="pipe-2",
        steps=[("step_1", "repo_connector")],
    )
    run_state.mark_step_status("step_1", StepStatus.RUNNING, started_at="t1")
    run_state.mark_step_status("step_1", StepStatus.SUCCESS, finished_at="t2")
    run_state.set_run_status(StepStatus.SUCCESS)

    payload = run_state.to_dict()
    restored = PipelineRunState.from_dict(payload)

    assert restored.run_id == "run-2"
    assert restored.pipeline_name == "pipe-2"
    assert restored.steps[0].status == StepStatus.SUCCESS
    assert restored.run_status == StepStatus.SUCCESS.value
