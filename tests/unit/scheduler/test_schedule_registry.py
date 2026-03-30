from __future__ import annotations

from scheduler.schedule_registry import (
    ScheduleRegistry,
    ScheduleSpec,
    build_default_schedule_registry,
)


def test_default_schedule_registry_contains_foundation_jobs():
    registry = build_default_schedule_registry()
    names = [item.job_name for item in registry.list_all()]

    assert "issue_scanner" in names
    assert "ci_monitor" in names
    assert "dependency_checker" in names
    issue_scanner = registry.get("issue_scanner")
    assert issue_scanner.default_inputs["labels"] == [
        "agent:opened",
        "agent:planning",
        "agent:ready",
        "agent:fixed",
    ]


def test_schedule_registry_supports_enable_disable_flags():
    registry = ScheduleRegistry()
    registry.register(
        ScheduleSpec(
            job_name="job_a",
            cron="*/5 * * * *",
            interval_seconds=300,
            pipeline_name="pipeline_a",
            enabled=True,
        )
    )
    registry.set_enabled("job_a", False)

    assert registry.get("job_a").enabled is False
    assert registry.list_enabled() == []
