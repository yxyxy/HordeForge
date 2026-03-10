from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logging_utils import redact_mapping

LOGGER = logging.getLogger("hordeforge.scheduler.jobs.backup_runner")


@dataclass(frozen=True)
class BackupScriptResult:
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
        "component": "backup_runner_job",
        "event": event,
        **safe_fields,
    }
    LOGGER.log(level, json.dumps(payload, ensure_ascii=False))


class BackupRunnerJob:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path(__file__).resolve().parents[2]

    def _script_path(self, name: str) -> Path:
        return self._base_dir / "scripts" / "backup" / name

    def _run_script(self, script: Path, *, dry_run: bool) -> BackupScriptResult:
        args = [sys.executable, str(script)]
        if dry_run:
            args.append("--dry-run")

        _log_event(
            logging.INFO,
            "backup_script_start",
            script=str(script),
            dry_run=dry_run,
        )
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
        stdout = _truncate(completed.stdout.strip() if completed.stdout else None)
        stderr = _truncate(completed.stderr.strip() if completed.stderr else None)
        _log_event(
            logging.INFO if completed.returncode == 0 else logging.ERROR,
            "backup_script_end",
            script=str(script),
            dry_run=dry_run,
            return_code=completed.returncode,
        )
        return BackupScriptResult(
            script=str(script),
            return_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run", False))
        run_postgres = bool(payload.get("run_postgres", True))
        run_storage = bool(payload.get("run_storage", True))

        results: list[BackupScriptResult] = []
        if run_postgres:
            results.append(self._run_script(self._script_path("postgres_backup.py"), dry_run=dry_run))
        if run_storage:
            results.append(self._run_script(self._script_path("storage_backup.py"), dry_run=dry_run))

        success = all(item.return_code == 0 for item in results)
        return {
            "status": "SUCCESS" if success else "FAILED",
            "dry_run": dry_run,
            "run_postgres": run_postgres,
            "run_storage": run_storage,
            "results": [item.__dict__ for item in results],
        }
