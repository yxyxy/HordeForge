from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from storage.backends import StorageBackend, get_storage_backend
from storage.models import RunRecord

_DEFAULT_TABLE_NAME = "hordeforge_runs"


class RunRepository:
    def __init__(
        self,
        storage_dir: str = ".hordeforge_data",
        *,
        backend: StorageBackend | None = None,
        backend_type: str | None = None,
        table_name: str | None = None,
    ) -> None:
        if backend is None:
            resolved_type = backend_type or os.getenv("HORDEFORGE_STORAGE_BACKEND", "json")
            if resolved_type == "json":
                file_path = Path(storage_dir) / "runs.json"
                backend = get_storage_backend("json", file_path=file_path)
            else:
                backend = get_storage_backend(
                    resolved_type,
                    table_name=table_name or _DEFAULT_TABLE_NAME,
                )
        self.store = backend

    # ---------------- normalization ----------------

    @staticmethod
    def _normalize_tenant_id(value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "default"

    @staticmethod
    def _normalize_repository_full_name(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None

    @classmethod
    def _extract_tenant_from_run_id(cls, run_id: str | None) -> str | None:
        if not run_id or ":" not in run_id:
            return None

        tenant, remainder = str(run_id).split(":", 1)

        tenant = tenant.strip().lower()
        if not tenant or not remainder.strip():
            return None

        return cls._normalize_tenant_id(tenant)

    @classmethod
    def _resolve_tenant_id(cls, run_id: str, tenant_id: str | None) -> str | None:
        return (
            cls._normalize_tenant_id(tenant_id)
            if tenant_id
            else cls._extract_tenant_from_run_id(run_id)
        )

    # ---------------- persistence ----------------

    def _load(self) -> list[RunRecord]:
        records: list[RunRecord] = []

        for item in self.store.read_all():
            try:
                records.append(RunRecord.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue

        return records

    def _save(self, items: Iterable[RunRecord]) -> None:
        self.store.write_all([item.to_dict() for item in items])

    # ---------------- record normalization ----------------

    def _normalize_record(self, record: RunRecord) -> RunRecord:
        inferred = self._extract_tenant_from_run_id(record.run_id)

        record.tenant_id = self._normalize_tenant_id(inferred or record.tenant_id)

        record.repository_full_name = self._normalize_repository_full_name(
            record.repository_full_name
        )

        return record

    # ---------------- CRUD ----------------

    def create(self, record: RunRecord) -> RunRecord:
        record = self._normalize_record(record)
        items = self._load()

        if any(r.run_id == record.run_id and r.tenant_id == record.tenant_id for r in items):
            raise ValueError(f"Run '{record.run_id}' already exists")

        items.append(record)
        self._save(items)

        return record

    def upsert(self, record: RunRecord) -> RunRecord:
        record = self._normalize_record(record)
        items = self._load()

        for i, item in enumerate(items):
            if item.run_id == record.run_id and item.tenant_id == record.tenant_id:
                items[i] = record
                self._save(items)
                return record

        items.append(record)
        self._save(items)

        return record

    def get(self, run_id: str, *, tenant_id: str | None = None) -> RunRecord | None:
        run_id = run_id.strip()
        tenant = self._resolve_tenant_id(run_id, tenant_id)

        matches = [r for r in self._load() if r.run_id == run_id]

        if tenant is None:
            return matches[0] if len(matches) == 1 else None

        for item in matches:
            if item.tenant_id == tenant:
                return item

        return None

    def delete(self, run_id: str, *, tenant_id: str | None = None) -> bool:
        run_id = run_id.strip()
        tenant = self._resolve_tenant_id(run_id, tenant_id)

        items = self._load()

        filtered = [
            item
            for item in items
            if not (item.run_id == run_id and (tenant is None or item.tenant_id == tenant))
        ]

        if len(filtered) == len(items):
            return False

        self._save(filtered)
        return True

    # ---------------- date parsing ----------------

    @staticmethod
    def _parse_started_at(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_filter_date(value: str | None) -> datetime | None:
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # ---------------- filtering ----------------

    def _filter_items(
        self,
        items: Iterable[RunRecord],
        *,
        run_id: str | None,
        tenant: str | None,
        pipeline_name: str | None,
        status: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[RunRecord]:

        result = []

        for item in items:
            if run_id and item.run_id != run_id:
                continue

            if tenant and item.tenant_id != tenant:
                continue

            if pipeline_name and item.pipeline_name != pipeline_name:
                continue

            if status and item.status != status:
                continue

            started = self._parse_started_at(item.started_at)

            if date_from and started < date_from:
                continue

            if date_to and started > date_to:
                continue

            result.append(item)

        return result

    # ---------------- listing ----------------

    def list(
        self,
        *,
        run_id: str | None = None,
        tenant_id: str | None = None,
        pipeline_name: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RunRecord]:

        run_id = run_id.strip() if run_id else None
        tenant = (
            self._resolve_tenant_id(run_id, tenant_id)
            if run_id
            else (self._normalize_tenant_id(tenant_id) if tenant_id else None)
        )

        items = self._filter_items(
            self._load(),
            run_id=run_id,
            tenant=tenant,
            pipeline_name=pipeline_name,
            status=status,
            date_from=self._parse_filter_date(date_from),
            date_to=self._parse_filter_date(date_to),
        )

        items.sort(
            key=lambda r: self._parse_started_at(r.started_at),
            reverse=True,
        )

        offset = max(0, int(offset))
        limit = max(1, min(200, int(limit)))

        return items[offset : offset + limit]
