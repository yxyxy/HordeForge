from __future__ import annotations

from enum import Enum


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class InvalidStatusTransition(ValueError):
    pass


VALID_STATUS_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.SKIPPED, StepStatus.BLOCKED},
    StepStatus.RUNNING: {
        StepStatus.SUCCESS,
        StepStatus.FAILED,
        StepStatus.BLOCKED,
        StepStatus.SKIPPED,
    },
    StepStatus.SUCCESS: {StepStatus.RUNNING},
    StepStatus.FAILED: {StepStatus.RUNNING, StepStatus.SKIPPED},
    StepStatus.BLOCKED: {StepStatus.RUNNING},
    StepStatus.SKIPPED: {StepStatus.RUNNING},
}


def can_transition(current_status: StepStatus, next_status: StepStatus) -> bool:
    if current_status == next_status:
        return True
    return next_status in VALID_STATUS_TRANSITIONS[current_status]


def ensure_valid_transition(current_status: StepStatus, next_status: StepStatus) -> None:
    if not can_transition(current_status, next_status):
        raise InvalidStatusTransition(
            f"Invalid step status transition: {current_status.value} -> {next_status.value}"
        )
