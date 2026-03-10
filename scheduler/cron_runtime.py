from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from logging_utils import redact_mapping
from scheduler.cron_dispatcher import CronDispatcher, JobHandler
from scheduler.idempotency import build_idempotency_key
from scheduler.jobs import (
    BackupRunnerJob,
    CiMonitorJob,
    DataRetentionJob,
    DependencyCheckerJob,
    IssueScannerJob,
)
from scheduler.schedule_registry import build_default_schedule_registry

TriggerPipelineFn = Callable[[str, dict[str, Any], str, str | None], dict[str, Any]]

LOGGER = logging.getLogger("hordeforge.cron_runtime")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(level: int, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    run_id = safe_fields.pop("run_id", None)
    correlation_id = safe_fields.pop("correlation_id", None)
    step = safe_fields.pop("step", safe_fields.pop("step_name", None))
    payload = {
        "timestamp": _utc_now_iso(),
        "level": logging.getLevelName(level),
        "component": "cron_runtime",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "step": step,
        "event": event,
        **safe_fields,
    }
    LOGGER.log(level, json.dumps(payload, ensure_ascii=False))


def _publish_triggers(
    *,
    job_name: str,
    triggers: list[dict[str, Any]],
    trigger_pipeline: TriggerPipelineFn,
) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    for index, trigger in enumerate(triggers):
        pipeline_name = str(trigger.get("pipeline_name", "")).strip()
        if not pipeline_name:
            continue

        raw_inputs = trigger.get("inputs")
        inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
        raw_idempotency_key = trigger.get("idempotency_key")
        idempotency_key = (
            raw_idempotency_key.strip()
            if isinstance(raw_idempotency_key, str) and raw_idempotency_key.strip()
            else build_idempotency_key(
                source=f"cron:{job_name}:{index}",
                pipeline_name=pipeline_name,
                payload=inputs,
            )
        )
        response = trigger_pipeline(pipeline_name, inputs, f"cron:{job_name}", idempotency_key)
        published.append(
            {
                "pipeline_name": pipeline_name,
                "idempotency_key": idempotency_key,
                "response": response,
            }
        )
        _log_event(
            logging.INFO,
            "cron_trigger_published",
            job_name=job_name,
            pipeline_name=pipeline_name,
            idempotency_key=idempotency_key,
            trigger_status=response.get("status"),
            run_id=response.get("run_id"),
        )
    return published


def _build_job_handler(
    *,
    job_name: str,
    run_job: Callable[[dict[str, Any]], dict[str, Any]],
    trigger_pipeline: TriggerPipelineFn,
) -> JobHandler:
    def _handler(payload: dict[str, Any]) -> dict[str, Any]:
        result = run_job(payload if isinstance(payload, dict) else {})
        raw_triggers = result.get("triggers", [])
        triggers = (
            [item for item in raw_triggers if isinstance(item, dict)]
            if isinstance(raw_triggers, list)
            else []
        )
        published: list[dict[str, Any]] = []
        if triggers:
            published = _publish_triggers(
                job_name=job_name,
                triggers=triggers,
                trigger_pipeline=trigger_pipeline,
            )
        enriched = dict(result)
        enriched["published_triggers"] = published
        enriched["published_count"] = len(published)
        return enriched

    return _handler


def build_default_job_handlers(trigger_pipeline: TriggerPipelineFn) -> dict[str, JobHandler]:
    issue_scanner = IssueScannerJob()
    ci_monitor = CiMonitorJob()
    dependency_checker = DependencyCheckerJob()
    backup_runner = BackupRunnerJob()
    data_retention = DataRetentionJob()

    return {
        "issue_scanner": _build_job_handler(
            job_name="issue_scanner",
            run_job=issue_scanner.run,
            trigger_pipeline=trigger_pipeline,
        ),
        "ci_monitor": _build_job_handler(
            job_name="ci_monitor",
            run_job=ci_monitor.run,
            trigger_pipeline=trigger_pipeline,
        ),
        "dependency_checker": _build_job_handler(
            job_name="dependency_checker",
            run_job=dependency_checker.run,
            trigger_pipeline=trigger_pipeline,
        ),
        "backup_runner": _build_job_handler(
            job_name="backup_runner",
            run_job=backup_runner.run,
            trigger_pipeline=trigger_pipeline,
        ),
        "data_retention": _build_job_handler(
            job_name="data_retention",
            run_job=data_retention.run,
            trigger_pipeline=trigger_pipeline,
        ),
    }


def build_default_cron_dispatcher(trigger_pipeline: TriggerPipelineFn) -> CronDispatcher:
    registry = build_default_schedule_registry()
    dispatcher = CronDispatcher()
    dispatcher.register_from_schedule_registry(
        registry=registry,
        handlers=build_default_job_handlers(trigger_pipeline),
    )
    return dispatcher
