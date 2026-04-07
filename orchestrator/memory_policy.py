from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MemoryPromotionPolicy:
    """Policy that decides when short-term entries can be promoted to long-term memory."""

    allowed_run_statuses: set[str] | None = None
    blocked_step_statuses: set[str] | None = None
    allowed_entry_types: set[str] | None = None

    def __post_init__(self) -> None:
        if self.allowed_run_statuses is None:
            self.allowed_run_statuses = {"SUCCESS", "PARTIAL_SUCCESS"}
        if self.blocked_step_statuses is None:
            self.blocked_step_statuses = {"FAILED", "BLOCKED"}
        if self.allowed_entry_types is None:
            self.allowed_entry_types = {"task", "patch"}

    def should_promote(
        self,
        *,
        run_status: str,
        step_result: dict[str, Any],
        entry_payload: dict[str, Any] | None = None,
    ) -> bool:
        normalized_run_status = str(run_status or "").strip().upper()
        if normalized_run_status not in self.allowed_run_statuses:
            return False

        step_status = str(step_result.get("status") or "").strip().upper()
        if step_status in self.blocked_step_statuses:
            return False

        if self._is_unstable(step_result=step_result, entry_payload=entry_payload):
            return False

        entry_type = str((entry_payload or {}).get("type") or "").strip().lower()
        if entry_type and entry_type not in self.allowed_entry_types:
            return False

        return True

    @staticmethod
    def _is_unstable(
        *,
        step_result: dict[str, Any],
        entry_payload: dict[str, Any] | None,
    ) -> bool:
        if bool(step_result.get("fallback_generated")):
            return True

        result_payload = step_result.get("result")
        if isinstance(result_payload, dict) and str(result_payload.get("source", "")).strip() == (
            "memory_agent_fallback"
        ):
            return True

        payload = entry_payload if isinstance(entry_payload, dict) else {}
        if str(payload.get("note", "")).strip() == "fallback_empty_patch":
            return True

        artifacts = step_result.get("artifacts", [])
        if isinstance(artifacts, list):
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, dict):
                    continue
                if str(content.get("source", "")).strip() == "memory_agent_fallback":
                    return True
                if str(content.get("note", "")).strip() == "fallback_empty_patch":
                    return True

        return False
