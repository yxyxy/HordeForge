from orchestrator.state import PipelineRunState, StepStatus


def test_engine_sets_run_status_safely():
    """Test that engine sets run status using the lock."""
    state = PipelineRunState(run_id="test", pipeline_name="test")

    # Verify initial status
    assert state.run_status == StepStatus.PENDING.value

    # Set status using set_run_status (which acquires the lock)
    state.set_run_status(StepStatus.SUCCESS)

    # Verify status was set correctly
    assert state.run_status == StepStatus.SUCCESS.value


def test_pipeline_run_state_thread_safety():
    """Test that PipelineRunState is thread-safe."""
    import threading

    state = PipelineRunState(run_id="test", pipeline_name="test")
    errors = []

    def set_status(status):
        try:
            state.set_run_status(status)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=set_status, args=(StepStatus.SUCCESS,)),
        threading.Thread(target=set_status, args=(StepStatus.FAILED,)),
        threading.Thread(target=set_status, args=(StepStatus.BLOCKED,)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert state.run_status in {
        StepStatus.SUCCESS.value,
        StepStatus.FAILED.value,
        StepStatus.BLOCKED.value,
    }
