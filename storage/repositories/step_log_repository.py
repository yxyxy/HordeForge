from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from storage.models import StepLogRecord
from storage.persistence import JsonStore


class StepLogRepository:
    def __init__(self, storage_dir: str = ".hordeforge_data") -> None:
        path = Path(storage_dir) / "step_logs.json"
        self.store = JsonStore(path)

    def _load(self) -> list[StepLogRecord]:
        records: list[StepLogRecord] = []
        for item in self.store.read_all():
            try:
                records.append(StepLogRecord.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return records

    def _save(self, items: list[StepLogRecord]) -> None:
        self.store.write_all([item.to_dict() for item in items])

    def add_many(self, records: list[StepLogRecord]) -> None:
        if not records:
            return
        items = self._load()
        for record in records:
            items.append(
                StepLogRecord(
                    run_id=str(record.run_id).strip(),
                    step_name=record.step_name,
                    status=record.status,
                    tenant_id=str(record.tenant_id or "").strip().lower() or "default",
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                    error=record.error,
                    retry_count=record.retry_count,
                )
            )
        self._save(items)

    def replace_for_run(
        self,
        run_id: str,
        records: list[StepLogRecord],
        *,
        tenant_id: str | None = None,
    ) -> None:
        normalized_tenant = str(tenant_id or "").strip().lower() or "default"
        normalized_run_id = str(run_id).strip()
        items = [
            item
            for item in self._load()
            if not (item.run_id == normalized_run_id and (item.tenant_id == normalized_tenant))
        ]
        for record in records:
            items.append(
                StepLogRecord(
                    run_id=normalized_run_id,
                    step_name=record.step_name,
                    status=record.status,
                    tenant_id=normalized_tenant,
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                    error=record.error,
                    retry_count=record.retry_count,
                )
            )
        self._save(items)

    def list_by_run(self, run_id: str, *, tenant_id: str | None = None) -> list[StepLogRecord]:
        def _parse(value: str | None) -> datetime:
            if not value:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)

        normalized_tenant = str(tenant_id or "").strip().lower() or "default"
        normalized_run_id = str(run_id).strip()
        filtered = [
            item
            for item in self._load()
            if item.run_id == normalized_run_id and item.tenant_id == normalized_tenant
        ]
        filtered.sort(key=lambda item: (_parse(item.started_at), item.step_name))
        return filtered
