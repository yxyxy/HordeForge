from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path

from storage.backends import StorageBackend, get_storage_backend
from storage.models import ArtifactRecord

_DEFAULT_TABLE_NAME = "hordeforge_artifacts"


class ArtifactRepository:
    def __init__(
        self,
        storage_dir: str = ".hordeforge_data",
        *,
        max_artifact_bytes: int = 200_000,
        allowed_artifact_types: Iterable[str] | None = None,
        backend: StorageBackend | None = None,
        backend_type: str | None = None,
        table_name: str | None = None,
    ) -> None:
        if backend is None:
            resolved_type = backend_type or os.getenv("HORDEFORGE_STORAGE_BACKEND", "json")
            if resolved_type == "json":
                path = Path(storage_dir) / "artifacts.json"
                backend = get_storage_backend("json", file_path=path)
            else:
                backend = get_storage_backend(
                    resolved_type,
                    table_name=table_name or _DEFAULT_TABLE_NAME,
                )
        self.store = backend
        self.max_artifact_bytes = max(1, int(max_artifact_bytes))
        if allowed_artifact_types is None:
            self.allowed_artifact_types = None
        else:
            normalized = {
                value.strip()
                for value in allowed_artifact_types
                if isinstance(value, str) and value.strip()
            }
            self.allowed_artifact_types = normalized or None

    def _load(self) -> list[ArtifactRecord]:
        records: list[ArtifactRecord] = []
        for item in self.store.read_all():
            try:
                records.append(ArtifactRecord.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return records

    def _save(self, items: list[ArtifactRecord]) -> None:
        self.store.write_all([item.to_dict() for item in items])

    def _compute_size(self, content: dict) -> int:
        encoded = json.dumps(content, ensure_ascii=False).encode("utf-8")
        return len(encoded)

    @staticmethod
    def _build_type_index(items: list[ArtifactRecord]) -> dict[str, list[ArtifactRecord]]:
        index: dict[str, list[ArtifactRecord]] = {}
        for item in items:
            index.setdefault(item.artifact_type, []).append(item)
        return index

    def replace_for_run(
        self,
        run_id: str,
        records: list[ArtifactRecord],
        *,
        tenant_id: str | None = None,
    ) -> None:
        normalized_tenant = str(tenant_id or "").strip().lower() or "default"
        normalized_run_id = str(run_id).strip()
        filtered: list[ArtifactRecord] = []
        for record in records:
            if not isinstance(record.content, dict):
                continue
            artifact_type = record.artifact_type.strip() or "unknown"
            if (
                self.allowed_artifact_types is not None
                and artifact_type not in self.allowed_artifact_types
            ):
                continue
            size = self._compute_size(record.content)
            if size > self.max_artifact_bytes:
                continue
            filtered.append(
                ArtifactRecord(
                    run_id=normalized_run_id,
                    step_name=record.step_name,
                    artifact_type=artifact_type,
                    content=record.content,
                    size_bytes=size,
                    tenant_id=normalized_tenant,
                )
            )

        items: list[ArtifactRecord] = []
        for item in self._load():
            if item.run_id != normalized_run_id:
                items.append(item)
                continue
            if item.tenant_id != normalized_tenant:
                items.append(item)
        items.extend(filtered)
        self._save(items)

    def list_by_run(self, run_id: str, *, tenant_id: str | None = None) -> list[ArtifactRecord]:
        normalized_tenant = str(tenant_id or "").strip().lower() or "default"
        normalized_run_id = str(run_id).strip()
        return [
            item
            for item in self._load()
            if item.run_id == normalized_run_id and item.tenant_id == normalized_tenant
        ]

    def list_by_type(
        self,
        artifact_type: str,
        *,
        tenant_id: str | None = None,
    ) -> list[ArtifactRecord]:
        normalized = artifact_type.strip()
        if not normalized:
            return []
        normalized_tenant = str(tenant_id or "").strip().lower() or "default"
        items = [item for item in self._load() if item.tenant_id == normalized_tenant]
        index = self._build_type_index(items)
        return list(index.get(normalized, []))
