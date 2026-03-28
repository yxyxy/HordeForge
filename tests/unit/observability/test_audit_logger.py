from __future__ import annotations

from observability.audit_logger import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    get_audit_logger,
    log_auth_event,
    log_pipeline_completed,
    log_pipeline_started,
    log_run_override,
)


def test_audit_event_creation():
    """Test audit event creation."""
    event = AuditEvent(
        event_id="test-1",
        event_type="test_event",
        timestamp="2026-03-09T10:00:00+00:00",
        tenant_id="test-tenant",
        actor="user@example.com",
        resource="run/123",
        action="test_action",
        result="success",
    )
    assert event.event_id == "test-1"
    assert event.tenant_id == "test-tenant"


def test_audit_logger_log():
    """Test audit logger basic logging."""
    logger = AuditLogger()
    event = logger.log(
        event_type=AuditEventType.PIPELINE_STARTED,
        tenant_id="test-tenant",
        action="start_pipeline",
        result="started",
    )

    assert event.tenant_id == "test-tenant"
    assert event.event_type == AuditEventType.PIPELINE_STARTED.value
    assert logger.get_events_count("test-tenant") == 1


def test_audit_logger_query():
    """Test audit logger query."""
    logger = AuditLogger()
    # Log multiple events
    logger.log(AuditEventType.PIPELINE_STARTED, "tenant-1", "start", "started")
    logger.log(AuditEventType.PIPELINE_COMPLETED, "tenant-1", "complete", "success")
    logger.log(AuditEventType.PIPELINE_STARTED, "tenant-2", "start", "started")

    # Query by tenant
    results = logger.query(tenant_id="tenant-1")
    assert len(results) == 2

    # Query by event type
    results = logger.query(event_type=AuditEventType.PIPELINE_STARTED)
    assert len(results) == 2


def test_audit_logger_query_limit():
    """Test audit logger query limit."""
    logger = AuditLogger()
    for i in range(20):
        logger.log(AuditEventType.PIPELINE_STARTED, "tenant-1", f"action_{i}", "started")

    results = logger.query(tenant_id="tenant-1", limit=5)
    assert len(results) == 5


def test_log_pipeline_started():
    """Test convenience function for pipeline start."""
    event = log_pipeline_started(
        tenant_id="test-tenant",
        pipeline_name="feature_pipeline",
        run_id="run-123",
    )
    assert event.event_type == AuditEventType.PIPELINE_STARTED.value
    assert event.details["pipeline_name"] == "feature_pipeline"


def test_log_pipeline_completed():
    """Test convenience function for pipeline completion."""
    event = log_pipeline_completed(
        tenant_id="test-tenant",
        pipeline_name="feature_pipeline",
        run_id="run-123",
        duration_seconds=120.5,
    )
    assert event.event_type == AuditEventType.PIPELINE_COMPLETED.value
    assert event.details["duration_seconds"] == 120.5


def test_log_run_override():
    """Test convenience function for run override."""
    event = log_run_override(
        tenant_id="test-tenant",
        run_id="run-123",
        override_action="stop",
        actor="admin@example.com",
    )
    assert event.event_type == AuditEventType.RUN_OVERRIDE.value
    assert event.actor == "admin@example.com"
    assert event.details["override_action"] == "stop"


def test_log_auth_event_success():
    """Test authentication success logging."""
    event = log_auth_event(
        tenant_id="test-tenant",
        success=True,
        actor="user@example.com",
    )
    assert event.event_type == AuditEventType.AUTH_SUCCESS.value


def test_log_auth_event_failure():
    """Test authentication failure logging."""
    event = log_auth_event(
        tenant_id="test-tenant",
        success=False,
        actor="unknown@example.com",
        reason="Invalid API key",
    )
    assert event.event_type == AuditEventType.AUTH_FAILURE.value
    assert event.details["reason"] == "Invalid API key"


def test_get_audit_logger_singleton():
    """Test audit logger singleton."""
    logger1 = get_audit_logger()
    logger2 = get_audit_logger()
    assert logger1 is logger2
