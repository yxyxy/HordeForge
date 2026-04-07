from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from orchestrator.pipeline_state import PipelineState
from orchestrator.status import StepStatus


@dataclass(slots=True)
class ExecutionContext:
    run_id: str
    pipeline_name: str
    inputs: dict[str, Any] = field(default_factory=dict)

    # NEW
    trigger_type: str | None = None

    state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    pipeline_state: PipelineState | None = None

    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.state:
            self.state = dict(self.inputs)
        if self.pipeline_state is None:
            self.pipeline_state = PipelineState.from_legacy_state(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                legacy_state=self.state,
            )

    def update_state(self, updates: dict[str, Any]) -> None:
        with self._lock:
            self.state.update(updates)
            self.pipeline_state.artifacts.update(updates)

    def set_state_value(self, key: str, value: Any) -> None:
        with self._lock:
            self.state[key] = value
            self.pipeline_state.artifacts[key] = value

    def record_step_result(self, step_name: str, result: dict[str, Any]) -> None:
        with self._lock:
            self.step_results[step_name] = result
            self.state[step_name] = result
            self.pipeline_state.artifacts[step_name] = result
            self.pipeline_state.current_step = step_name

    def sync_pipeline_state_from_run_state(self, run_state: Any) -> None:
        with self._lock:
            completed: set[str] = set()
            failed: list[str] = []
            retry_state: dict[str, int] = {}
            current_step: str | None = None

            raw_steps = getattr(run_state, "steps", [])
            for item in raw_steps:
                step_name = str(getattr(item, "name", "")).strip()
                if not step_name:
                    continue

                status = getattr(item, "status", None)
                status_value = status.value if hasattr(status, "value") else str(status or "")
                attempts = int(getattr(item, "attempts", 0) or 0)
                retry_state[step_name] = max(0, attempts - 1)

                if status_value in {
                    StepStatus.SUCCESS.value,
                    StepStatus.PARTIAL_SUCCESS.value,
                    StepStatus.SKIPPED.value,
                }:
                    completed.add(step_name)
                elif status_value in {StepStatus.FAILED.value, StepStatus.BLOCKED.value}:
                    failed.append(step_name)
                    current_step = step_name
                elif status_value == StepStatus.RUNNING.value:
                    current_step = step_name

            all_steps = [str(getattr(item, "name", "")).strip() for item in raw_steps]
            pending = [
                name
                for name in all_steps
                if name and name not in completed and name not in failed and name != current_step
            ]
            if current_step and current_step not in pending and current_step in all_steps:
                pending.insert(0, current_step)

            locks = self.state.get("__locks")
            if not isinstance(locks, list):
                locks = []
            normalized_locks = [str(item) for item in locks if str(item).strip()]

            self.pipeline_state.current_step = current_step
            self.pipeline_state.pending_steps = pending
            self.pipeline_state.failed_steps = failed
            self.pipeline_state.retry_state = retry_state
            self.pipeline_state.locks = normalized_locks

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "pipeline_name": self.pipeline_name,
                "trigger_type": self.trigger_type,
                "inputs": dict(self.inputs),
                "state": dict(self.state),
                "metadata": dict(self.metadata),
                "step_results": dict(self.step_results),
                "pipeline_state": self.pipeline_state.model_dump(mode="json"),
            }
