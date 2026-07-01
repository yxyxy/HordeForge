from __future__ import annotations

from enum import Enum


class PipelineStatus(str, Enum):
    """Formal lifecycle states for a pipeline run."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    STEP_EXECUTING = "STEP_EXECUTING"
    LOOPING = "LOOPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class InvalidPipelineTransition(ValueError):
    """Raised when an invalid pipeline state transition is attempted."""


PIPELINE_TRANSITIONS: dict[PipelineStatus, set[PipelineStatus]] = {
    PipelineStatus.CREATED: {PipelineStatus.VALIDATING, PipelineStatus.CANCELLED},
    PipelineStatus.VALIDATING: {
        PipelineStatus.RUNNING,
        PipelineStatus.FAILED,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.RUNNING: {
        PipelineStatus.STEP_EXECUTING,
        PipelineStatus.LOOPING,
        PipelineStatus.COMPLETED,
        PipelineStatus.FAILED,
        PipelineStatus.BLOCKED,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.STEP_EXECUTING: {
        PipelineStatus.RUNNING,
        PipelineStatus.LOOPING,
        PipelineStatus.COMPLETED,
        PipelineStatus.FAILED,
        PipelineStatus.BLOCKED,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.LOOPING: {
        PipelineStatus.RUNNING,
        PipelineStatus.STEP_EXECUTING,
        PipelineStatus.COMPLETED,
        PipelineStatus.FAILED,
        PipelineStatus.BLOCKED,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.COMPLETED: set(),
    PipelineStatus.FAILED: {PipelineStatus.RUNNING, PipelineStatus.CANCELLED},
    PipelineStatus.BLOCKED: {PipelineStatus.RUNNING, PipelineStatus.CANCELLED},
    PipelineStatus.CANCELLED: set(),
}


def can_pipeline_transition(current: PipelineStatus, next_status: PipelineStatus) -> bool:
    """Check whether a pipeline transition is valid."""
    if current == next_status:
        return True
    return next_status in PIPELINE_TRANSITIONS.get(current, set())


def ensure_valid_pipeline_transition(current: PipelineStatus, next_status: PipelineStatus) -> None:
    """Raise InvalidPipelineTransition if the transition is not allowed."""
    if not can_pipeline_transition(current, next_status):
        raise InvalidPipelineTransition(
            f"Invalid pipeline transition: {current.value} -> {next_status.value}"
        )
