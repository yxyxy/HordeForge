from __future__ import annotations

import logging
import threading
from typing import Any

from orchestrator.memory_policy import MemoryPromotionPolicy
from orchestrator.status import StepStatus
from rag.memory_collections import MemoryType, create_memory_entry
from rag.memory_store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryHook:
    """Hook for memory capture and optional deferred promotion."""

    SHORT_TERM_KEY = "__short_term_memory_entries"
    PROMOTION_MODE_KEY = "__memory_promotion_mode"

    def __init__(self, memory_store: MemoryStore, policy: MemoryPromotionPolicy | None = None):
        self.memory_store = memory_store
        self.policy = policy or MemoryPromotionPolicy()

    def after_step(
        self, step_name: str, step_result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        status = str(step_result.get("status", "")).strip().upper()
        if status not in {StepStatus.SUCCESS.value, "SUCCESS", "MERGED", "PARTIAL_SUCCESS"}:
            return

        memory_entry = self._create_memory_entry(step_name, step_result, context)
        if not memory_entry:
            return

        short_term_entries = context.setdefault(self.SHORT_TERM_KEY, [])
        if isinstance(short_term_entries, list):
            short_term_entries.append(
                {
                    "step_name": step_name,
                    "step_result": dict(step_result),
                    "entry": memory_entry.to_dict(),
                    "task_description": memory_entry.task_description,
                }
            )

        promotion_mode = str(context.get(self.PROMOTION_MODE_KEY, "immediate")).strip().lower()
        if promotion_mode == "deferred":
            return

        try:
            self.memory_store.add_memory(
                memory_entry.task_description, payload=memory_entry.to_dict()
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Error saving memory entry: %s", e)

    def promote_short_term(self, *, context: dict[str, Any], run_status: str) -> int:
        entries = context.get(self.SHORT_TERM_KEY)
        if not isinstance(entries, list) or not entries:
            return 0

        promoted = 0
        for item in entries:
            if not isinstance(item, dict):
                continue
            step_result = item.get("step_result")
            payload = item.get("entry")
            task_description = str(item.get("task_description") or "").strip()
            if not isinstance(step_result, dict) or not isinstance(payload, dict):
                continue
            if not task_description:
                continue
            if not self.policy.should_promote(
                run_status=run_status,
                step_result=step_result,
                entry_payload=payload,
            ):
                continue

            try:
                self.memory_store.add_memory(task_description, payload=payload)
                promoted += 1
            except Exception as e:
                logger.warning("Failed to promote memory entry for '%s': %s", task_description, e)
                continue

        context[self.SHORT_TERM_KEY] = []
        return promoted

    def _create_memory_entry(
        self, step_name: str, step_result: dict[str, Any], context: dict[str, Any]
    ):
        task_description = context.get("task_description")
        if not task_description:
            issue = context.get("issue", "")
            if isinstance(issue, str):
                task_description = issue[:100]
            elif isinstance(issue, dict):
                task_description = issue.get("title", str(issue)[:100])
            else:
                task_description = str(issue)[:100]

        agents_used = context.get("agents_used", [])
        if not isinstance(agents_used, list):
            agents_used = []
            context["agents_used"] = agents_used

        if step_name not in agents_used:
            agents_used.append(step_name)

        result_status = step_result.get("status", "UNKNOWN")
        artifacts = step_result.get("artifacts", [])

        patch_artifacts = [a for a in artifacts if isinstance(a, dict) and a.get("type") == "patch"]
        if patch_artifacts:
            patch_data = patch_artifacts[0].get("content", {})
            return create_memory_entry(
                entry_type=MemoryType.PATCH,
                task_description=task_description,
                file=patch_data.get("file", ""),
                diff=patch_data.get("diff", ""),
                reason=patch_data.get("reason", ""),
                agents_used=agents_used,
                result_status=result_status,
            )

        if step_name == "review_agent":
            review_result = step_result.get("result", {})
            if isinstance(review_result, dict) and review_result.get("action") == "MERGE_APPROVED":
                return create_memory_entry(
                    entry_type=MemoryType.PATCH,
                    task_description=task_description,
                    file=review_result.get("file", ""),
                    diff=review_result.get("diff", ""),
                    reason=f"Review approved: {review_result.get('comment', '')}",
                    agents_used=agents_used,
                    result_status="MERGED",
                )

        return create_memory_entry(
            entry_type=MemoryType.TASK,
            task_description=task_description,
            pipeline=context.get("pipeline", ""),
            agents_used=agents_used,
            result_status=result_status,
        )


class ExecutionGuardrailHook:
    """Pre/post execution checks for orchestrator steps."""

    def before_step(self, *, step_name: str, context: dict[str, Any]) -> None:
        return None

    def after_step(
        self, *, step_name: str, output: dict[str, Any], context: dict[str, Any]
    ) -> None:
        return None


class BasicExecutionGuardrailHook(ExecutionGuardrailHook):
    """Default guardrails for permission and output contract checks."""

    STEP_PERMISSIONS_KEY = "__step_permissions"
    GRANTED_PERMISSIONS_KEY = "__granted_permissions"
    REQUIRED_OUTPUT_KEYS: tuple[str, ...] = (
        "status",
        "artifacts",
        "decisions",
        "logs",
        "next_actions",
    )

    def before_step(self, *, step_name: str, context: dict[str, Any]) -> None:
        permissions_map = context.get(self.STEP_PERMISSIONS_KEY)
        if not isinstance(permissions_map, dict):
            return
        required_raw = permissions_map.get(step_name, [])
        if isinstance(required_raw, str):
            required = [required_raw]
        elif isinstance(required_raw, list):
            required = [str(item).strip() for item in required_raw if str(item).strip()]
        else:
            required = []
        if not required:
            return

        granted_raw = context.get(self.GRANTED_PERMISSIONS_KEY, [])
        if isinstance(granted_raw, str):
            granted = {granted_raw.strip()} if granted_raw.strip() else set()
        elif isinstance(granted_raw, list):
            granted = {str(item).strip() for item in granted_raw if str(item).strip()}
        else:
            granted = set()

        missing = sorted(item for item in required if item not in granted)
        if missing:
            raise PermissionError(f"missing_permissions_for_step:{step_name}:{','.join(missing)}")

    def after_step(
        self, *, step_name: str, output: dict[str, Any], context: dict[str, Any]
    ) -> None:
        if not isinstance(output, dict):
            raise ValueError(f"invalid_step_output_type:{step_name}")
        missing_keys = [key for key in self.REQUIRED_OUTPUT_KEYS if key not in output]
        if missing_keys:
            raise ValueError(f"missing_output_keys:{step_name}:{','.join(missing_keys)}")
        if not isinstance(output.get("artifacts"), list):
            raise ValueError(f"invalid_output_artifacts_type:{step_name}")


_active_memory_hook: MemoryHook | None = None
_memory_hook_lock = threading.Lock()


def register_memory_hook(hook: MemoryHook) -> None:
    global _active_memory_hook
    with _memory_hook_lock:
        _active_memory_hook = hook


def get_memory_hook() -> MemoryHook | None:
    with _memory_hook_lock:
        return _active_memory_hook


def trigger_memory_hook(
    step_name: str, step_result: dict[str, Any], context: dict[str, Any]
) -> None:
    hook = get_memory_hook()
    if hook:
        hook.after_step(step_name, step_result, context)


def trigger_memory_promotion(context: dict[str, Any], run_status: str) -> int:
    hook = get_memory_hook()
    if hook is None:
        return 0
    return hook.promote_short_term(context=context, run_status=run_status)
