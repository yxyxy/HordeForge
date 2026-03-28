from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scheduler.cron_dispatcher import CronDispatcher
from scheduler.schedule_registry import ScheduleRegistry, ScheduleSpec


def test_cron_dispatcher_runs_due_jobs_by_interval():
    state = {"runs": 0}

    def _job(_payload: dict) -> dict:
        state["runs"] += 1
        return {"runs": state["runs"]}

    dispatcher = CronDispatcher()
    dispatcher.register_job("issue_scanner", _job, interval_seconds=60)

    t0 = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    first = dispatcher.run_due_jobs(now=t0)
    second = dispatcher.run_due_jobs(now=t0 + timedelta(seconds=30))
    third = dispatcher.run_due_jobs(now=t0 + timedelta(seconds=61))

    assert len(first) == 1
    assert len(second) == 0
    assert len(third) == 1
    assert state["runs"] == 2


def test_cron_dispatcher_supports_manual_trigger_for_registered_job():
    def _job(payload: dict) -> dict:
        return {"received": payload.get("source")}

    dispatcher = CronDispatcher()
    dispatcher.register_job("manual_job", _job, interval_seconds=3600)

    result = dispatcher.trigger_job("manual_job", payload={"source": "manual-test"})

    assert result["status"] == "SUCCESS"
    assert result["trigger"] == "manual"
    assert result["result"]["received"] == "manual-test"


def test_cron_dispatcher_logs_start_end_for_job_run(caplog):
    def _job(_payload: dict) -> dict:
        return {"ok": True}

    dispatcher = CronDispatcher()
    dispatcher.register_job("log_job", _job, interval_seconds=60)

    with caplog.at_level("INFO", logger="hordeforge.cron_dispatcher"):
        dispatcher.trigger_job("log_job")

    assert any("cron_job_start" in record.message for record in caplog.records)
    assert any("cron_job_end" in record.message for record in caplog.records)


def test_cron_dispatcher_unknown_job_raises():
    dispatcher = CronDispatcher()

    with pytest.raises(KeyError):
        dispatcher.trigger_job("missing_job")


def test_cron_dispatcher_registers_enabled_jobs_from_schedule_registry():
    registry = ScheduleRegistry()
    registry.register(
        ScheduleSpec(
            job_name="job_enabled",
            cron="*/5 * * * *",
            interval_seconds=300,
            pipeline_name="pipe",
            enabled=True,
            default_inputs={"source": "registry-default"},
        )
    )
    registry.register(
        ScheduleSpec(
            job_name="job_disabled",
            cron="*/5 * * * *",
            interval_seconds=300,
            pipeline_name="pipe",
            enabled=False,
        )
    )
    dispatcher = CronDispatcher()
    dispatcher.register_from_schedule_registry(
        registry,
        handlers={"job_enabled": lambda payload: {"ok": True, "source": payload.get("source")}},
    )
    run_result = dispatcher.trigger_job("job_enabled")

    assert "job_enabled" in dispatcher.jobs
    assert "job_disabled" not in dispatcher.jobs
    assert run_result["result"]["source"] == "registry-default"


def test_cron_dispatcher_merges_default_payload_with_manual_payload():
    seen_payload: dict[str, object] = {}

    def _job(payload: dict) -> dict:
        seen_payload.update(payload)
        return payload

    dispatcher = CronDispatcher()
    dispatcher.register_job(
        "merge_payload_job",
        _job,
        interval_seconds=60,
        default_payload={"a": 1, "shared": "default"},
    )

    result = dispatcher.trigger_job("merge_payload_job", payload={"b": 2, "shared": "manual"})

    assert result["status"] == "SUCCESS"
    assert seen_payload == {"a": 1, "b": 2, "shared": "manual"}
