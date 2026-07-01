"""Shared utilities for orchestrator modules."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def is_step_success(result: dict[str, Any]) -> bool:
    """Check if a step result indicates success."""
    return result.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}


def log_event(
    logger: Any,
    level: int,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    step_name: str | None = None,
) -> None:
    """Log a structured event."""
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if step_name:
        payload["step"] = step_name
    logger.log(level, json.dumps(payload, ensure_ascii=False))
