from __future__ import annotations

from datetime import timedelta

from observability.alerts import AlertDispatcher


def test_alert_dispatcher_sends_for_failed_and_blocked(caplog):
    dispatcher = AlertDispatcher(throttle_seconds=60)

    with caplog.at_level("ERROR", logger="hordeforge.alerts"):
        failed_sent = dispatcher.alert_run_failure(
            run_id="run-1",
            pipeline_name="init_pipeline",
            status="FAILED",
            correlation_id="corr-1",
            error="boom",
        )
        blocked_sent = dispatcher.alert_run_failure(
            run_id="run-2",
            pipeline_name="init_pipeline",
            status="BLOCKED",
            correlation_id="corr-2",
            error="manual stop",
        )

    assert failed_sent is True
    assert blocked_sent is True
    assert any('"status": "FAILED"' in record.message for record in caplog.records)
    assert any('"status": "BLOCKED"' in record.message for record in caplog.records)


def test_alert_dispatcher_ignores_non_critical_status():
    dispatcher = AlertDispatcher(throttle_seconds=60)

    sent = dispatcher.alert_run_failure(
        run_id="run-1",
        pipeline_name="init_pipeline",
        status="SUCCESS",
        correlation_id="corr-1",
        error=None,
    )

    assert sent is False


def test_alert_dispatcher_throttles_same_pipeline_and_status():
    dispatcher = AlertDispatcher(throttle_seconds=300)
    first = dispatcher.alert_run_failure(
        run_id="run-1",
        pipeline_name="init_pipeline",
        status="FAILED",
        correlation_id="corr-1",
        error="boom",
    )
    second = dispatcher.alert_run_failure(
        run_id="run-2",
        pipeline_name="init_pipeline",
        status="FAILED",
        correlation_id="corr-2",
        error="boom-again",
    )

    key = "init_pipeline:FAILED"
    dispatcher._last_alert_at[key] = dispatcher._last_alert_at[key] - timedelta(seconds=301)
    third = dispatcher.alert_run_failure(
        run_id="run-3",
        pipeline_name="init_pipeline",
        status="FAILED",
        correlation_id="corr-3",
        error="boom-third",
    )

    assert first is True
    assert second is False
    assert third is True
