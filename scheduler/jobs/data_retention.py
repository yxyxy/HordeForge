from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logging_utils import redact_mapping

LOGGER = logging.getLogger("hordeforge.scheduler.jobs.data_retention")


@dataclass(frozen=True)
class CleanupResult:
    script: str
    return_code: int
    stdout: str | None = None
    stderr: str | None = None


def _truncate(value: str | None, limit: int = 500) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _log_event(level: int, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    payload = {
        "component": "data_retention_job",
        "event": event,
        **safe_fields,
    }
    LOGGER.log(level, json.dumps(payload, ensure_ascii=False))


class DataRetentionJob:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path(__file__).resolve().parents[2]

    def _script_path(self, name: str) -> Path:
        return self._base_dir / "scripts" / "cleanup" / name

    def _run_script(
        self,
        script: Path,
        *,
        dry_run: bool,
        retention_days: int | None,
        storage_dir: str | None,
    ) -> CleanupResult:
        args = [sys.executable, str(script)]
        if storage_dir:
            args.extend(["--storage-dir", storage_dir])
        if retention_days is not None:
            args.extend(["--retention-days", str(retention_days)])
        if dry_run:
            args.append("--dry-run")

        _log_event(
            logging.INFO,
            "cleanup_script_start",
            script=str(script),
            dry_run=dry_run,
            retention_days=retention_days,
        )
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
        stdout = _truncate(completed.stdout.strip() if completed.stdout else None)
        stderr = _truncate(completed.stderr.strip() if completed.stderr else None)
        _log_event(
            logging.INFO if completed.returncode == 0 else logging.ERROR,
            "cleanup_script_end",
            script=str(script),
            dry_run=dry_run,
            return_code=completed.returncode,
        )
        return CleanupResult(
            script=str(script),
            return_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run", False))
        retention_runs = payload.get("retention_runs_days")
        retention_logs = payload.get("retention_logs_days")
        retention_artifacts = payload.get("retention_artifacts_days")
        retention_audit = payload.get("retention_audit_days")
        storage_dir = payload.get("storage_dir")

        results: list[CleanupResult] = []
        results.append(
            self._run_script(
                self._script_path("cleanup_runs.py"),
                dry_run=dry_run,
                retention_days=retention_runs,
                storage_dir=storage_dir,
            )
        )
        results.append(
            self._run_script(
                self._script_path("cleanup_step_logs.py"),
                dry_run=dry_run,
                retention_days=retention_logs,
                storage_dir=storage_dir,
            )
        )
        results.append(
            self._run_script(
                self._script_path("cleanup_artifacts.py"),
                dry_run=dry_run,
                retention_days=retention_artifacts,
                storage_dir=storage_dir,
            )
        )
        results.append(
            self._run_script(
                self._script_path("cleanup_audit.py"),
                dry_run=dry_run,
                retention_days=retention_audit,
                storage_dir=storage_dir,
            )
        )

        success = all(item.return_code == 0 for item in results)
        return {
            "status": "SUCCESS" if success else "FAILED",
            "dry_run": dry_run,
            "results": [item.__dict__ for item in results],
        }
