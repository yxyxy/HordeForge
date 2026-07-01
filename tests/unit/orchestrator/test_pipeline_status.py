from __future__ import annotations

import pytest

from orchestrator.pipeline_status import (
    InvalidPipelineTransition,
    PipelineStatus,
    can_pipeline_transition,
    ensure_valid_pipeline_transition,
)
from orchestrator.state import PipelineRunState

# ---------------------------------------------------------------------------
# 1. All valid transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current, expected_targets",
    [
        (
            PipelineStatus.CREATED,
            {PipelineStatus.VALIDATING, PipelineStatus.CANCELLED},
        ),
        (
            PipelineStatus.VALIDATING,
            {PipelineStatus.RUNNING, PipelineStatus.FAILED, PipelineStatus.CANCELLED},
        ),
        (
            PipelineStatus.RUNNING,
            {
                PipelineStatus.STEP_EXECUTING,
                PipelineStatus.LOOPING,
                PipelineStatus.COMPLETED,
                PipelineStatus.FAILED,
                PipelineStatus.BLOCKED,
                PipelineStatus.CANCELLED,
            },
        ),
        (
            PipelineStatus.STEP_EXECUTING,
            {
                PipelineStatus.RUNNING,
                PipelineStatus.LOOPING,
                PipelineStatus.COMPLETED,
                PipelineStatus.FAILED,
                PipelineStatus.BLOCKED,
                PipelineStatus.CANCELLED,
            },
        ),
        (
            PipelineStatus.LOOPING,
            {
                PipelineStatus.RUNNING,
                PipelineStatus.STEP_EXECUTING,
                PipelineStatus.COMPLETED,
                PipelineStatus.FAILED,
                PipelineStatus.BLOCKED,
                PipelineStatus.CANCELLED,
            },
        ),
    ],
)
def test_valid_transitions(current: PipelineStatus, expected_targets: set[PipelineStatus]) -> None:
    for target in expected_targets:
        assert can_pipeline_transition(current, target), (
            f"{current.value} -> {target.value} should be valid"
        )
        ensure_valid_pipeline_transition(current, target)


# ---------------------------------------------------------------------------
# 2. Invalid transitions raise InvalidPipelineTransition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current, target",
    [
        (PipelineStatus.CREATED, PipelineStatus.RUNNING),
        (PipelineStatus.CREATED, PipelineStatus.STEP_EXECUTING),
        (PipelineStatus.CREATED, PipelineStatus.LOOPING),
        (PipelineStatus.CREATED, PipelineStatus.COMPLETED),
        (PipelineStatus.CREATED, PipelineStatus.FAILED),
        (PipelineStatus.CREATED, PipelineStatus.BLOCKED),
        (PipelineStatus.COMPLETED, PipelineStatus.RUNNING),
        (PipelineStatus.COMPLETED, PipelineStatus.CREATED),
        (PipelineStatus.COMPLETED, PipelineStatus.VALIDATING),
        (PipelineStatus.CANCELLED, PipelineStatus.RUNNING),
        (PipelineStatus.CANCELLED, PipelineStatus.CREATED),
        (PipelineStatus.VALIDATING, PipelineStatus.CREATED),
        (PipelineStatus.VALIDATING, PipelineStatus.STEP_EXECUTING),
        (PipelineStatus.RUNNING, PipelineStatus.CREATED),
        (PipelineStatus.RUNNING, PipelineStatus.VALIDATING),
        (PipelineStatus.STEP_EXECUTING, PipelineStatus.CREATED),
        (PipelineStatus.STEP_EXECUTING, PipelineStatus.VALIDATING),
        (PipelineStatus.LOOPING, PipelineStatus.CREATED),
        (PipelineStatus.LOOPING, PipelineStatus.VALIDATING),
    ],
)
def test_invalid_transition_raises(current: PipelineStatus, target: PipelineStatus) -> None:
    assert not can_pipeline_transition(current, target)
    with pytest.raises(InvalidPipelineTransition, match=f"{current.value} -> {target.value}"):
        ensure_valid_pipeline_transition(current, target)


# ---------------------------------------------------------------------------
# 3. Terminal states have no outgoing transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("terminal", [PipelineStatus.COMPLETED, PipelineStatus.CANCELLED])
def test_terminal_states_no_outgoing(terminal: PipelineStatus) -> None:
    for target in PipelineStatus:
        if target == terminal:
            continue
        assert not can_pipeline_transition(terminal, target), (
            f"Terminal state {terminal.value} should not transition to {target.value}"
        )


# ---------------------------------------------------------------------------
# 4. FAILED can transition to RUNNING (resume)
# ---------------------------------------------------------------------------


def test_failed_can_transition_to_running() -> None:
    assert can_pipeline_transition(PipelineStatus.FAILED, PipelineStatus.RUNNING)
    ensure_valid_pipeline_transition(PipelineStatus.FAILED, PipelineStatus.RUNNING)


def test_failed_can_transition_to_cancelled() -> None:
    assert can_pipeline_transition(PipelineStatus.FAILED, PipelineStatus.CANCELLED)


# ---------------------------------------------------------------------------
# 5. BLOCKED can transition to RUNNING (unblock)
# ---------------------------------------------------------------------------


def test_blocked_can_transition_to_running() -> None:
    assert can_pipeline_transition(PipelineStatus.BLOCKED, PipelineStatus.RUNNING)
    ensure_valid_pipeline_transition(PipelineStatus.BLOCKED, PipelineStatus.RUNNING)


def test_blocked_can_transition_to_cancelled() -> None:
    assert can_pipeline_transition(PipelineStatus.BLOCKED, PipelineStatus.CANCELLED)


# ---------------------------------------------------------------------------
# 6. Same-state transition is always valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(PipelineStatus))
def test_same_state_transition_always_valid(status: PipelineStatus) -> None:
    assert can_pipeline_transition(status, status)
    ensure_valid_pipeline_transition(status, status)


# ---------------------------------------------------------------------------
# 7. PipelineRunState integration
# ---------------------------------------------------------------------------


def _make_run_state(
    pipeline_status: PipelineStatus = PipelineStatus.CREATED,
) -> PipelineRunState:
    return PipelineRunState.from_steps(
        run_id="run-test",
        pipeline_name="pipe-test",
        steps=[("step_a", "agent_a"), ("step_b", "agent_b")],
    )


class TestPipelineRunStateTransitionPipeline:
    def test_transition_updates_pipeline_status(self) -> None:
        state = _make_run_state()
        state.transition_pipeline(PipelineStatus.VALIDATING)
        assert state.pipeline_status == PipelineStatus.VALIDATING

    def test_transition_chain(self) -> None:
        state = _make_run_state()
        state.transition_pipeline(PipelineStatus.VALIDATING)
        state.transition_pipeline(PipelineStatus.RUNNING)
        state.transition_pipeline(PipelineStatus.STEP_EXECUTING)
        state.transition_pipeline(PipelineStatus.RUNNING)
        state.transition_pipeline(PipelineStatus.COMPLETED)
        assert state.pipeline_status == PipelineStatus.COMPLETED

    def test_invalid_transition_raises(self) -> None:
        state = _make_run_state()
        with pytest.raises(InvalidPipelineTransition):
            state.transition_pipeline(PipelineStatus.RUNNING)

    def test_terminal_blocks_further_transitions(self) -> None:
        state = _make_run_state()
        state.transition_pipeline(PipelineStatus.VALIDATING)
        state.transition_pipeline(PipelineStatus.RUNNING)
        state.transition_pipeline(PipelineStatus.COMPLETED)
        with pytest.raises(InvalidPipelineTransition):
            state.transition_pipeline(PipelineStatus.RUNNING)


class TestPipelineRunStateSerialization:
    def test_to_dict_includes_pipeline_status(self) -> None:
        state = _make_run_state()
        state.transition_pipeline(PipelineStatus.VALIDATING)
        state.transition_pipeline(PipelineStatus.RUNNING)
        payload = state.to_dict()
        assert payload["pipeline_status"] == "RUNNING"

    def test_to_dict_from_dict_roundtrip(self) -> None:
        state = _make_run_state()
        state.transition_pipeline(PipelineStatus.VALIDATING)
        state.transition_pipeline(PipelineStatus.RUNNING)
        state.transition_pipeline(PipelineStatus.STEP_EXECUTING)

        payload = state.to_dict()
        restored = PipelineRunState.from_dict(payload)

        assert restored.run_id == state.run_id
        assert restored.pipeline_name == state.pipeline_name
        assert restored.pipeline_status == PipelineStatus.STEP_EXECUTING
        assert len(restored.steps) == 2

    def test_from_dict_missing_pipeline_status_defaults_to_running(self) -> None:
        payload = {
            "run_id": "run-old",
            "pipeline_name": "pipe-old",
            "steps": [],
        }
        restored = PipelineRunState.from_dict(payload)
        assert restored.pipeline_status == PipelineStatus.RUNNING

    def test_from_dict_with_explicit_pipeline_status(self) -> None:
        payload = {
            "run_id": "run-x",
            "pipeline_name": "pipe-x",
            "pipeline_status": "FAILED",
            "steps": [],
        }
        restored = PipelineRunState.from_dict(payload)
        assert restored.pipeline_status == PipelineStatus.FAILED

    def test_roundtrip_preserves_all_fields(self) -> None:
        state = PipelineRunState.from_steps(
            run_id="run-full",
            pipeline_name="pipe-full",
            steps=[("s1", "a1"), ("s2", "a2")],
            correlation_id="corr-1",
            trace_id="trace-1",
        )
        state.transition_pipeline(PipelineStatus.VALIDATING)
        state.transition_pipeline(PipelineStatus.RUNNING)

        payload = state.to_dict()
        restored = PipelineRunState.from_dict(payload)

        assert restored.correlation_id == "corr-1"
        assert restored.trace_id == "trace-1"
        assert restored.pipeline_status == PipelineStatus.RUNNING
        assert restored.steps[0].name == "s1"
        assert restored.steps[1].agent == "a2"
