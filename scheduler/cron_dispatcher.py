from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from logging_utils import redact_mapping
from scheduler.schedule_registry import ScheduleRegistry

JobHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(slots=True)
class CronJob:
    name: str
    interval_seconds: int
    handler: JobHandler
    enabled: bool = True
    default_payload: dict[str, Any] = field(default_factory=dict)
    last_run_at: datetime | None = None


class CronDispatcher:
    def __init__(self) -> None:
        self.jobs: dict[str, CronJob] = {}
        self.logger = logging.getLogger("hordeforge.cron_dispatcher")

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_event(self, level: int, event: str, **fields: Any) -> None:
        safe_fields = redact_mapping(fields)
        run_id = safe_fields.pop("run_id", None)
        correlation_id = safe_fields.pop("correlation_id", None)
        step = safe_fields.pop("step", safe_fields.pop("step_name", None))
        payload = {
            "timestamp": self._utc_now_iso(),
            "level": logging.getLevelName(level),
            "component": "cron_dispatcher",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "step": step,
            "event": event,
            **safe_fields,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    def register_job(
        self,
        name: str,
        handler: JobHandler,
        *,
        interval_seconds: int,
        enabled: bool = True,
        default_payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("job name must be a non-empty string")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if normalized_name in self.jobs:
            raise ValueError(f"Job '{normalized_name}' is already registered")
        self.jobs[normalized_name] = CronJob(
            name=normalized_name,
            interval_seconds=interval_seconds,
            handler=handler,
            enabled=enabled,
            default_payload=dict(default_payload or {}),
        )

    def register_from_schedule_registry(
        self,
        registry: ScheduleRegistry,
        handlers: dict[str, JobHandler],
    ) -> None:
        for spec in registry.list_enabled():
            handler = handlers.get(spec.job_name)
            if handler is None:
                continue
            if spec.job_name in self.jobs:
                continue
            self.register_job(
                spec.job_name,
                handler,
                interval_seconds=spec.interval_seconds,
                enabled=spec.enabled,
                default_payload=spec.default_inputs,
            )

    @staticmethod
    def _merge_payload(job: CronJob, payload: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(job.default_payload)
        if isinstance(payload, dict):
            merged.update(payload)
        return merged

    def _is_due(self, job: CronJob, now: datetime) -> bool:
        if not job.enabled:
            return False
        if job.last_run_at is None:
            return True
        return now >= job.last_run_at + timedelta(seconds=job.interval_seconds)

    def _run_job(
        self,
        job: CronJob,
        *,
        trigger: str,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        started_at = now or self._utc_now()
        self._log_event(
            logging.INFO,
            "cron_job_start",
            job_name=job.name,
            trigger=trigger,
            started_at=started_at.isoformat(),
        )

        status = "SUCCESS"
        error: str | None = None
        result_payload: dict[str, Any] | None = None
        effective_payload = self._merge_payload(job, payload)
        try:
            raw_result = job.handler(effective_payload)
            result_payload = raw_result if isinstance(raw_result, dict) else {}
        except Exception as exc:  # noqa: BLE001
            status = "FAILED"
            error = str(exc)
            result_payload = {}
            self._log_event(
                logging.ERROR,
                "cron_job_error",
                job_name=job.name,
                trigger=trigger,
                error=str(exc),
            )

        finished_at = self._utc_now()
        job.last_run_at = started_at
        record = {
            "job_name": job.name,
            "trigger": trigger,
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": error,
            "result": result_payload,
        }
        self._log_event(
            logging.INFO if status == "SUCCESS" else logging.ERROR,
            "cron_job_end",
            job_name=job.name,
            trigger=trigger,
            status=status,
            finished_at=finished_at.isoformat(),
            error=error,
        )
        return record

    def run_due_jobs(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current_time = now or self._utc_now()
        records: list[dict[str, Any]] = []
        for job in self.jobs.values():
            if not self._is_due(job, current_time):
                continue
            records.append(self._run_job(job, trigger="schedule", now=current_time))
        return records

    def trigger_job(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        job = self.jobs.get(name)
        if not job:
            raise KeyError(f"Unknown cron job: {name}")
        return self._run_job(job, trigger="manual", payload=payload or {})
