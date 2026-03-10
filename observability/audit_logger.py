from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any


class AuditEventType(Enum):
    """Types of audit events."""

    # Pipeline events
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"

    # Manual control events
    RUN_OVERRIDE = "run_override"
    RUN_STOPPED = "run_stopped"
    RUN_RETRY = "run_retry"
    RUN_RESUMED = "run_resumed"

    # Tenant events
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DELETED = "tenant_deleted"

    # Security events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    PERMISSION_DENIED = "permission_denied"

    # Configuration events
    CONFIG_CHANGED = "config_changed"


@dataclass
class AuditEvent:
    """Audit event structure."""

    event_id: str
    event_type: str
    timestamp: str
    tenant_id: str
    actor: str | None
    resource: str | None
    action: str
    result: str
    details: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    trace_id: str | None = None


class AuditLogger:
    """Multi-tenant audit logger."""

    def __init__(
        self,
        log_dir: str | None = None,
        retention_days: int = 90,
    ) -> None:
        self._log_dir = log_dir or os.getenv(
            "HORDEFORGE_AUDIT_LOG_DIR", ".hordeforge_data/audit"
        )
        self._retention_days = retention_days
        self._logger = logging.getLogger("hordeforge.audit")
        self._lock = RLock()
        self._events: list[AuditEvent] = []

    def log(
        self,
        event_type: AuditEventType,
        tenant_id: str,
        action: str,
        result: str,
        actor: str | None = None,
        resource: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        """Log an audit event."""
        import uuid

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type.value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tenant_id=tenant_id,
            actor=actor,
            resource=resource,
            action=action,
            result=result,
            details=details or {},
            correlation_id=correlation_id,
            trace_id=trace_id,
        )

        with self._lock:
            self._events.append(event)
            self._persist_event(event)

        self._logger.info(
            f"AUDIT: {event_type.value} tenant={tenant_id} action={action} result={result}"
        )

        return event

    def _persist_event(self, event: AuditEvent) -> None:
        """Persist event to file."""
        try:
            import pathlib

            log_path = pathlib.Path(self._log_dir)
            log_path.mkdir(parents=True, exist_ok=True)

            # Partition by date
            date_str = event.timestamp[:10]
            file_path = log_path / f"audit_{date_str}.jsonl"

            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._event_to_dict(event)) + "\n")
        except Exception as e:
            self._logger.error(f"Failed to persist audit event: {e}")

    def _event_to_dict(self, event: AuditEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "tenant_id": event.tenant_id,
            "actor": event.actor,
            "resource": event.resource,
            "action": event.action,
            "result": event.result,
            "details": event.details,
            "correlation_id": event.correlation_id,
            "trace_id": event.trace_id,
        }

    def query(
        self,
        tenant_id: str | None = None,
        event_type: AuditEventType | None = None,
        actor: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit events."""
        with self._lock:
            events = self._events.copy()

        # Apply filters
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type.value]
        if actor:
            events = [e for e in events if e.actor == actor]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        events = events[:limit]

        return [self._event_to_dict(e) for e in events]

    def get_events_count(self, tenant_id: str | None = None) -> int:
        """Get total events count."""
        with self._lock:
            if tenant_id:
                return sum(1 for e in self._events if e.tenant_id == tenant_id)
            return len(self._events)


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def log_pipeline_started(
    tenant_id: str,
    pipeline_name: str,
    run_id: str,
    correlation_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    """Log pipeline start event."""
    return get_audit_logger().log(
        event_type=AuditEventType.PIPELINE_STARTED,
        tenant_id=tenant_id,
        action=f"start_{pipeline_name}",
        result="started",
        resource=f"run/{run_id}",
        details={"pipeline_name": pipeline_name},
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


def log_pipeline_completed(
    tenant_id: str,
    pipeline_name: str,
    run_id: str,
    duration_seconds: float,
    correlation_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    """Log pipeline completion event."""
    return get_audit_logger().log(
        event_type=AuditEventType.PIPELINE_COMPLETED,
        tenant_id=tenant_id,
        action=f"complete_{pipeline_name}",
        result="success",
        resource=f"run/{run_id}",
        details={"pipeline_name": pipeline_name, "duration_seconds": duration_seconds},
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


def log_run_override(
    tenant_id: str,
    run_id: str,
    override_action: str,
    actor: str,
    correlation_id: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    """Log manual override event."""
    return get_audit_logger().log(
        event_type=AuditEventType.RUN_OVERRIDE,
        tenant_id=tenant_id,
        action=f"override_{override_action}",
        result="executed",
        resource=f"run/{run_id}",
        actor=actor,
        details={"override_action": override_action},
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


def log_auth_event(
    tenant_id: str,
    success: bool,
    actor: str | None = None,
    reason: str | None = None,
) -> AuditEvent:
    """Log authentication event."""
    return get_audit_logger().log(
        event_type=(
            AuditEventType.AUTH_SUCCESS if success else AuditEventType.AUTH_FAILURE
        ),
        tenant_id=tenant_id,
        action="authenticate",
        result="success" if success else "failure",
        actor=actor,
        details={"reason": reason} if reason else {},
    )
