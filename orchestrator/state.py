from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from orchestrator.status import StepStatus, ensure_valid_transition


@dataclass(slots=True)
class StepRunState:
    name: str
    agent: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    correlation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    output: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent": self.agent,
            "status": self.status.value,
            "attempts": self.attempts,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StepRunState:
        return cls(
            name=payload["name"],
            agent=payload["agent"],
            status=StepStatus(payload["status"]),
            attempts=payload.get("attempts", 0),
            correlation_id=payload.get("correlation_id"),
            trace_id=payload.get("trace_id"),
            span_id=payload.get("span_id"),
            parent_span_id=payload.get("parent_span_id"),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            error=payload.get("error"),
            output=payload.get("output"),
        )


@dataclass(slots=True)
class PipelineRunState:
    run_id: str
    pipeline_name: str
    correlation_id: str | None = None
    trace_id: str | None = None
    steps: list[StepRunState] = field(default_factory=list)
    current_step_index: int = 0
    run_status: str = StepStatus.PENDING.value
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    @classmethod
    def from_steps(
        cls,
        run_id: str,
        pipeline_name: str,
        steps: list[tuple[str, str]],
        *,
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> PipelineRunState:
        step_states = [StepRunState(name=name, agent=agent) for name, agent in steps]
        return cls(
            run_id=run_id,
            pipeline_name=pipeline_name,
            correlation_id=correlation_id,
            trace_id=trace_id,
            steps=step_states,
        )

    def get_step(self, step_name: str) -> StepRunState:
        with self._lock:
            for step in self.steps:
                if step.name == step_name:
                    return step
            raise KeyError(f"Step not found in run state: {step_name}")

    def mark_step_status(
        self,
        step_name: str,
        next_status: StepStatus,
        *,
        started_at: str | None = None,
        finished_at: str | None = None,
        error: str | None = None,
        output: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> StepRunState:
        with self._lock:
            step = self.get_step(step_name)
            ensure_valid_transition(step.status, next_status)

            step.status = next_status
            if next_status == StepStatus.RUNNING:
                step.attempts += 1
                step.started_at = started_at
                self.run_status = StepStatus.RUNNING.value
            if next_status in {
                StepStatus.SUCCESS,
                StepStatus.PARTIAL_SUCCESS,
                StepStatus.FAILED,
                StepStatus.BLOCKED,
                StepStatus.SKIPPED,
            }:
                step.finished_at = finished_at
            if error is not None:
                step.error = error
            if output is not None:
                step.output = output
            if correlation_id is not None:
                step.correlation_id = correlation_id
            if trace_id is not None:
                step.trace_id = trace_id
            if span_id is not None:
                step.span_id = span_id
            if parent_span_id is not None:
                step.parent_span_id = parent_span_id

            if next_status in {StepStatus.FAILED, StepStatus.BLOCKED}:
                self.run_status = next_status.value
            return step

    def set_run_status(self, next_status: StepStatus) -> None:
        with self._lock:
            self.run_status = next_status.value

    def advance_index(self) -> int:
        with self._lock:
            if self.current_step_index < len(self.steps):
                self.current_step_index += 1
            return self.current_step_index

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "pipeline_name": self.pipeline_name,
                "correlation_id": self.correlation_id,
                "trace_id": self.trace_id,
                "steps": [step.to_dict() for step in self.steps],
                "current_step_index": self.current_step_index,
                "run_status": self.run_status,
            }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PipelineRunState:
        return cls(
            run_id=payload["run_id"],
            pipeline_name=payload["pipeline_name"],
            correlation_id=payload.get("correlation_id"),
            trace_id=payload.get("trace_id"),
            steps=[StepRunState.from_dict(item) for item in payload.get("steps", [])],
            current_step_index=payload.get("current_step_index", 0),
            run_status=payload.get("run_status", StepStatus.PENDING.value),
        )
