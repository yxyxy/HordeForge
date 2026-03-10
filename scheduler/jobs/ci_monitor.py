from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from logging_utils import redact_mapping

LOGGER = logging.getLogger("hordeforge.scheduler.jobs.ci_monitor")


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
        "component": "ci_monitor_job",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "step": step,
        "event": event,
        **safe_fields,
    }
    LOGGER.log(level, json.dumps(payload, ensure_ascii=False))


class CiMonitorJob:
    def __init__(self) -> None:
        self._processed_run_ids: set[int] = set()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_runs = payload.get("workflow_runs", [])
        repository = payload.get("repository", {})
        if not isinstance(workflow_runs, list):
            workflow_runs = []

        triggers: list[dict[str, Any]] = []
        for run in workflow_runs:
            if not isinstance(run, dict):
                continue
            run_id = run.get("id")
            if not isinstance(run_id, int) or run_id in self._processed_run_ids:
                continue
            conclusion = str(run.get("conclusion", "")).lower()
            status = str(run.get("status", "")).lower()
            is_failed = conclusion in {"failure", "cancelled", "timed_out"} or status in {
                "failed",
                "failure",
            }
            if not is_failed:
                continue

            self._processed_run_ids.add(run_id)
            triggers.append(
                {
                    "pipeline_name": "ci_fix_pipeline",
                    "inputs": {
                        "repository": repository if isinstance(repository, dict) else {},
                        "ci_run": run,
                    },
                    "idempotency_key": f"ci_monitor:{run_id}",
                }
            )

        processed_run_ids = sorted(self._processed_run_ids)
        _log_event(
            logging.INFO,
            "ci_monitor_processed_runs",
            observed=len(workflow_runs),
            trigger_count=len(triggers),
            processed_run_ids=processed_run_ids,
        )
        return {
            "status": "SUCCESS",
            "observed": len(workflow_runs),
            "trigger_count": len(triggers),
            "processed_run_ids": processed_run_ids,
            "triggers": triggers,
        }
