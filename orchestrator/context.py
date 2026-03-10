from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


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

    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.state:
            self.state = dict(self.inputs)

    def update_state(self, updates: dict[str, Any]) -> None:
        with self._lock:
            self.state.update(updates)

    def set_state_value(self, key: str, value: Any) -> None:
        with self._lock:
            self.state[key] = value

    def record_step_result(self, step_name: str, result: dict[str, Any]) -> None:
        with self._lock:
            self.step_results[step_name] = result
            self.state[step_name] = result

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
            }