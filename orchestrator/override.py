from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

OverrideAction = Literal["stop", "retry", "resume", "explain"]


@dataclass(slots=True)
class OverrideRequest:
    run_id: str
    action: OverrideAction
    reason: str
    requested_at: str


class RunOverrideRegistry:
    def __init__(self) -> None:
        self._mapping: dict[str, OverrideRequest] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def set(self, run_id: str, action: OverrideAction, reason: str = "") -> OverrideRequest:
        request = OverrideRequest(
            run_id=run_id,
            action=action,
            reason=reason.strip(),
            requested_at=self._now_iso(),
        )
        self._mapping[run_id] = request
        return request

    def get(self, run_id: str) -> OverrideRequest | None:
        return self._mapping.get(run_id)

    def clear(self, run_id: str) -> None:
        self._mapping.pop(run_id, None)


RUN_OVERRIDE_REGISTRY = RunOverrideRegistry()
