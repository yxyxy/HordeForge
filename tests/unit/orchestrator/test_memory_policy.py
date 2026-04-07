from orchestrator.memory_policy import MemoryPromotionPolicy


def test_memory_policy_promotes_on_success_run_and_success_step():
    policy = MemoryPromotionPolicy()
    assert policy.should_promote(run_status="SUCCESS", step_result={"status": "SUCCESS"}) is True


def test_memory_policy_blocks_failed_run():
    policy = MemoryPromotionPolicy()
    assert policy.should_promote(run_status="FAILED", step_result={"status": "SUCCESS"}) is False


def test_memory_policy_blocks_failed_step():
    policy = MemoryPromotionPolicy()
    assert policy.should_promote(run_status="SUCCESS", step_result={"status": "FAILED"}) is False


def test_memory_policy_blocks_disallowed_entry_type():
    policy = MemoryPromotionPolicy()
    assert (
        policy.should_promote(
            run_status="SUCCESS",
            step_result={"status": "SUCCESS"},
            entry_payload={"type": "memory_context"},
        )
        is False
    )


def test_memory_policy_blocks_fallback_generated_payload():
    policy = MemoryPromotionPolicy()
    assert (
        policy.should_promote(
            run_status="SUCCESS",
            step_result={"status": "SUCCESS", "result": {"source": "memory_agent_fallback"}},
            entry_payload={"type": "task"},
        )
        is False
    )
