from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from observability.alerting import (
    format_alert_message,
    load_alerting_config,
    send_email_alert,
    send_slack_alert,
)


class AlertDispatcher:
    CRITICAL_STATUSES = {"FAILED", "BLOCKED"}
    BUDGET_WARNING_THRESHOLD = 0.8  # Alert at 80% of budget

    def __init__(self, *, throttle_seconds: int = 60) -> None:
        self.logger = logging.getLogger("hordeforge.alerts")
        self.throttle_seconds = max(1, int(throttle_seconds))
        self._last_alert_at: dict[str, datetime] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _should_alert(self, key: str) -> bool:
        now = self._now()
        last = self._last_alert_at.get(key)
        if last is not None and (now - last) < timedelta(seconds=self.throttle_seconds):
            return False
        self._last_alert_at[key] = now
        return True

    def alert_run_failure(
        self,
        *,
        run_id: str,
        pipeline_name: str,
        status: str,
        correlation_id: str,
        error: str | None = None,
    ) -> bool:
        normalized_status = str(status).upper()
        if normalized_status not in self.CRITICAL_STATUSES:
            return False

        key = f"{pipeline_name}:{normalized_status}"
        if not self._should_alert(key):
            return False
        payload: dict[str, Any] = {
            "event": "run_alert",
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "status": normalized_status,
            "correlation_id": correlation_id,
            "error": error,
        }
        self.logger.error(json.dumps(payload, ensure_ascii=False))
        config = load_alerting_config()
        message = format_alert_message(payload)
        slack_sent = False
        email_sent = False
        if config.slack:
            slack_sent = send_slack_alert(config.slack, message=message)
        if config.email:
            subject = f"HordeForge alert: {normalized_status}"
            email_sent = send_email_alert(config.email, subject=subject, body=message)
        has_destination = bool(config.slack or config.email)
        return (slack_sent or email_sent) if has_destination else True

    def alert_budget_exceeded(
        self,
        *,
        run_id: str,
        pipeline_name: str,
        cost_usd: float,
        budget_usd: float,
    ) -> bool:
        """Alert when a run exceeds its budget limit."""
        key = f"budget_exceeded:{run_id}"
        if not self._should_alert(key):
            return False
        payload: dict[str, Any] = {
            "event": "budget_exceeded",
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "cost_usd": cost_usd,
            "budget_usd": budget_usd,
        }
        self.logger.error(json.dumps(payload, ensure_ascii=False))
        return True

    def alert_budget_warning(
        self,
        *,
        run_id: str,
        pipeline_name: str,
        cost_usd: float,
        budget_usd: float,
    ) -> bool:
        """Alert when a run approaches its budget limit (80% threshold)."""
        if budget_usd <= 0:
            return False
        if (cost_usd / budget_usd) < self.BUDGET_WARNING_THRESHOLD:
            return False

        key = f"budget_warning:{run_id}"
        if not self._should_alert(key):
            return False
        percentage = (cost_usd / budget_usd) * 100
        payload: dict[str, Any] = {
            "event": "budget_warning",
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "cost_usd": cost_usd,
            "budget_usd": budget_usd,
            "budget_usage_percent": round(percentage, 1),
        }
        self.logger.warning(json.dumps(payload, ensure_ascii=False))
        return True
