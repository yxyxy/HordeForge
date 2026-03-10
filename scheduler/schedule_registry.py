from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    job_name: str
    cron: str
    interval_seconds: int
    pipeline_name: str
    enabled: bool = True
    default_inputs: dict[str, Any] = field(default_factory=dict)


class ScheduleRegistry:
    def __init__(self) -> None:
        self._mapping: dict[str, ScheduleSpec] = {}

    def register(self, spec: ScheduleSpec) -> None:
        if not spec.job_name.strip():
            raise ValueError("job_name must be non-empty")
        if spec.interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if spec.job_name in self._mapping:
            raise ValueError(f"Schedule '{spec.job_name}' already exists")
        self._mapping[spec.job_name] = spec

    def get(self, job_name: str) -> ScheduleSpec:
        if job_name not in self._mapping:
            raise KeyError(f"Schedule '{job_name}' is not registered")
        return self._mapping[job_name]

    def list_enabled(self) -> list[ScheduleSpec]:
        return [spec for spec in self._mapping.values() if spec.enabled]

    def list_all(self) -> list[ScheduleSpec]:
        return list(self._mapping.values())

    def set_enabled(self, job_name: str, enabled: bool) -> None:
        spec = self.get(job_name)
        self._mapping[job_name] = ScheduleSpec(
            job_name=spec.job_name,
            cron=spec.cron,
            interval_seconds=spec.interval_seconds,
            pipeline_name=spec.pipeline_name,
            enabled=bool(enabled),
            default_inputs=dict(spec.default_inputs),
        )


def build_default_schedule_registry() -> ScheduleRegistry:
    registry = ScheduleRegistry()
    registry.register(
        ScheduleSpec(
            job_name="issue_scanner",
            cron="*/15 * * * *",
            interval_seconds=900,
            pipeline_name="backlog_analysis_pipeline",
            enabled=True,
            default_inputs={"labels": ["agent:ready"]},
        )
    )
    registry.register(
        ScheduleSpec(
            job_name="ci_monitor",
            cron="*/10 * * * *",
            interval_seconds=600,
            pipeline_name="ci_monitoring_pipeline",
            enabled=True,
            default_inputs={"failed_only": True},
        )
    )
    registry.register(
        ScheduleSpec(
            job_name="dependency_checker",
            cron="0 */6 * * *",
            interval_seconds=21600,
            pipeline_name="dependency_check_pipeline",
            enabled=False,
            default_inputs={"critical_only": True},
        )
    )
    registry.register(
        ScheduleSpec(
            job_name="backup_runner",
            cron="0 2 * * *",
            interval_seconds=86400,
            pipeline_name="backup_runner",
            enabled=False,
            default_inputs={"dry_run": False},
        )
    )
    registry.register(
        ScheduleSpec(
            job_name="data_retention",
            cron="30 2 * * *",
            interval_seconds=86400,
            pipeline_name="data_retention",
            enabled=False,
            default_inputs={
                "dry_run": False,
                "retention_runs_days": 90,
                "retention_logs_days": 30,
                "retention_artifacts_days": 7,
                "retention_audit_days": 365,
            },
        )
    )
    return registry
