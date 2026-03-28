import pytest

from orchestrator.status import (
    InvalidStatusTransition,
    StepStatus,
    can_transition,
    ensure_valid_transition,
)


def test_step_status_contains_required_values():
    assert StepStatus.PENDING.value == "PENDING"
    assert StepStatus.RUNNING.value == "RUNNING"
    assert StepStatus.SUCCESS.value == "SUCCESS"
    assert StepStatus.FAILED.value == "FAILED"
    assert StepStatus.BLOCKED.value == "BLOCKED"
    assert StepStatus.SKIPPED.value == "SKIPPED"


def test_status_can_transition_pending_to_running():
    assert can_transition(StepStatus.PENDING, StepStatus.RUNNING)
    ensure_valid_transition(StepStatus.PENDING, StepStatus.RUNNING)


def test_status_allows_success_to_running_for_loop_reexecution():
    assert can_transition(StepStatus.SUCCESS, StepStatus.RUNNING)
    ensure_valid_transition(StepStatus.SUCCESS, StepStatus.RUNNING)


def test_status_rejects_invalid_transition():
    with pytest.raises(InvalidStatusTransition):
        ensure_valid_transition(StepStatus.SUCCESS, StepStatus.FAILED)


def test_status_allows_failed_to_skipped_transition():
    assert can_transition(StepStatus.FAILED, StepStatus.SKIPPED)
    ensure_valid_transition(StepStatus.FAILED, StepStatus.SKIPPED)


def test_status_rejects_blocked_to_success_transition():
    with pytest.raises(InvalidStatusTransition):
        ensure_valid_transition(StepStatus.BLOCKED, StepStatus.SUCCESS)
