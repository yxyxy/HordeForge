from __future__ import annotations

import gzip
import os
import re
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

LOG_FILENAMES = ("runs.json", "step_logs.json", "artifacts.json")
LOG_MAX_FILE_BYTES = 1_048_576


def get_current_log_path(storage_dir: str | Path, file_name: str) -> Path:
    return Path(storage_dir) / "logs" / "current" / file_name


def _format_timestamp_prefix(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def rotate_current_log_files(
    storage_dir: str | Path,
    *,
    container_started_at: datetime | None = None,
) -> list[Path]:
    started_at = container_started_at or datetime.now(timezone.utc)
    prefix = _format_timestamp_prefix(started_at)
    base_dir = Path(storage_dir)
    logs_dir = base_dir / "logs"
    current_dir = logs_dir / "current"
    logs_dir.mkdir(parents=True, exist_ok=True)
    rotated: list[Path] = []

    if not current_dir.exists():
        return rotated

    for file_name in LOG_FILENAMES:
        candidates = [current_dir / file_name, *sorted(current_dir.glob(f"{file_name}.part-*"))]
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            target = logs_dir / f"{prefix}__{candidate.name}"
            suffix = 1
            while target.exists():
                target = logs_dir / f"{prefix}__{candidate.name}.{suffix:03d}"
                suffix += 1
            candidate.replace(target)
            rotated.append(target)

    return rotated


def archive_and_prune_rotated_logs(
    storage_dir: str | Path,
    *,
    now: datetime | None = None,
    archive_after_days: int = 7,
    retention_days: int = 7,
) -> dict[str, int]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    archive_after = max(1, int(archive_after_days))
    retention = max(1, int(retention_days))
    logs_dir = Path(storage_dir) / "logs"
    archive_dir = logs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    compress_before = now_utc - timedelta(days=archive_after)
    delete_before = now_utc - timedelta(days=retention)

    compressed = 0
    deleted_archives = 0

    if logs_dir.exists():
        for item in logs_dir.iterdir():
            if not item.is_file():
                continue
            if ".gz" in item.suffixes:
                continue
            if "__" not in item.name:
                continue
            modified = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            if modified > compress_before:
                continue
            archive_path = archive_dir / f"{item.name}.gz"
            temp_path = archive_dir / f"{archive_path.name}.{uuid4().hex}.tmp"
            with item.open("rb") as source, gzip.open(temp_path, "wb") as target:
                shutil.copyfileobj(source, target)
            temp_path.replace(archive_path)
            item.unlink(missing_ok=True)
            compressed += 1

    if archive_dir.exists():
        for item in archive_dir.glob("*.gz"):
            modified = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            if modified > delete_before:
                continue
            item.unlink(missing_ok=True)
            deleted_archives += 1

    return {"compressed": compressed, "deleted_archives": deleted_archives}


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    def read_all(self) -> list[dict[str, Any]]:
        """Read all records."""
        raise NotImplementedError

    @abstractmethod
    def write_all(self, items: list[dict[str, Any]]) -> None:
        """Write all records, replacing existing."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        raise NotImplementedError

    def health_check(self) -> dict[str, Any]:
        """Return a basic health check payload."""
        return {
            "healthy": True,
            "backend": "unknown",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


class JsonStorageBackend(StorageBackend):
    """JSON file-based storage backend (current implementation)."""

    def __init__(self, file_path: str | Path) -> None:
        # Defer import to avoid circular dependency at module load
        import json
        import time
        from pathlib import Path
        from threading import RLock
        from uuid import uuid4

        self._file_path = Path(file_path)
        self._lock = RLock()
        self._json = json
        self._uuid4 = uuid4
        self._time = time
        self._max_file_bytes = LOG_MAX_FILE_BYTES
        self._part_rotation_enabled = self._file_path.name in LOG_FILENAMES
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._write_raw_to_path(self._file_path, [])

    def _write_raw_to_path(self, target_path: Path, payload: list[dict[str, Any]]) -> None:
        serialized = self._json.dumps(payload, ensure_ascii=False, indent=2)
        temp_path = target_path.with_suffix(f"{target_path.suffix}.{self._uuid4().hex}.tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        last_error: OSError | None = None
        for attempt in range(5):
            try:
                temp_path.replace(target_path)
                return
            except PermissionError as exc:
                last_error = exc
                self._time.sleep(0.01 * (attempt + 1))
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error

    def _payload_size_bytes(self, payload: list[dict[str, Any]]) -> int:
        return len(self._json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def _split_payload(self, payload: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if not payload:
            return [[]]
        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for item in payload:
            candidate = [*current, item]
            if current and self._payload_size_bytes(candidate) > self._max_file_bytes:
                chunks.append(current)
                current = [item]
                continue
            current = candidate
        if current:
            chunks.append(current)
        return chunks or [[]]

    def _part_index(self, path: Path) -> int:
        prefix = f"{self._file_path.name}.part-"
        if not path.name.startswith(prefix):
            return 0
        suffix = path.name[len(prefix) :]
        try:
            return int(suffix)
        except ValueError:
            return 0

    def _part_paths(self) -> list[Path]:
        return sorted(
            self._file_path.parent.glob(f"{self._file_path.name}.part-*"),
            key=self._part_index,
        )

    def _read_path_payload(self, path: Path) -> list[dict[str, Any]]:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            return []
        if not raw:
            return []
        try:
            payload = self._json.loads(raw)
        except self._json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _write_payload(self, payload: list[dict[str, Any]]) -> None:
        if not self._part_rotation_enabled:
            self._write_raw_to_path(self._file_path, payload)
            return
        chunks = self._split_payload(payload)
        expected_paths = [
            self._file_path,
            *[Path(f"{self._file_path}.part-{index:03d}") for index in range(1, len(chunks))],
        ]
        for index, chunk in enumerate(chunks):
            target = expected_paths[index]
            self._write_raw_to_path(target, chunk)
        expected = {path.resolve() for path in expected_paths}
        for path in self._part_paths():
            if path.resolve() not in expected:
                path.unlink(missing_ok=True)

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            paths = (
                [self._file_path, *self._part_paths()]
                if self._part_rotation_enabled
                else [self._file_path]
            )
            records: list[dict[str, Any]] = []
            for path in paths:
                records.extend(self._read_path_payload(path))
            return records

    def write_all(self, items: list[dict[str, Any]]) -> None:
        payload = [item for item in items if isinstance(item, dict)]
        with self._lock:
            self._write_payload(payload)

    def health_check(self) -> dict[str, Any]:
        try:
            self.read_all()
            return {
                "healthy": True,
                "backend": "json",
                "path": str(self._file_path),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "healthy": False,
                "backend": "json",
                "path": str(self._file_path),
                "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    def close(self) -> None:
        pass  # No connections to close


class PostgresStorageBackend(StorageBackend):
    """PostgreSQL storage backend for production use."""

    def __init__(
        self,
        *,
        connection_string: str | None = None,
        table_name: str = "hordeforge_data",
    ) -> None:
        self._connection_string = connection_string or os.getenv(
            "HORDEFORGE_POSTGRES_CONNECTION_STRING", ""
        )
        self._table_name = self._validate_table_name(table_name)
        self._conn = None
        self._ensure_connection()

    @staticmethod
    def _validate_table_name(table_name: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    def _ensure_connection(self) -> None:
        if self._conn is not None:
            return
        try:
            import psycopg2

            self._conn = psycopg2.connect(self._connection_string)
            self._create_table_if_not_exists()
        except ImportError as e:
            raise ImportError(
                "psycopg2 is required for PostgreSQL storage. "
                "Install with: pip install psycopg2-binary"
            ) from e
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to PostgreSQL: {exc}") from exc

    def _create_table_if_not_exists(self) -> None:
        if self._conn is None:
            return
        from psycopg2 import sql

        table = sql.Identifier(self._table_name)
        index = sql.Identifier(f"idx_{self._table_name}_key")
        with self._conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                CREATE TABLE IF NOT EXISTS {} (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) NOT NULL,
                    value JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
                ).format(table)
            )
            cur.execute(
                sql.SQL(
                    """
                CREATE INDEX IF NOT EXISTS {}
                ON {}(key);
                """
                ).format(index, table)
            )
            self._conn.commit()

    def read_all(self) -> list[dict[str, Any]]:
        self._ensure_connection()
        if self._conn is None:
            return []
        try:
            from psycopg2 import sql

            with self._conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT key, value FROM {}").format(sql.Identifier(self._table_name))
                )
                return [value for _, value in cur.fetchall()]
        except Exception:
            return []

    def write_all(self, items: list[dict[str, Any]]) -> None:
        self._ensure_connection()
        if self._conn is None:
            return
        try:
            from psycopg2 import sql

            with self._conn.cursor() as cur:
                # Clear existing data and insert new
                cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(self._table_name)))
                for item in items:
                    if isinstance(item, dict):
                        cur.execute(
                            sql.SQL("INSERT INTO {} (key, value) VALUES (%s, %s)").format(
                                sql.Identifier(self._table_name)
                            ),
                            (item.get("run_id", str(self._uuid4())), self._json.dumps(item)),
                        )
                self._conn.commit()
        except Exception:
            self._conn.rollback()

    def health_check(self) -> dict[str, Any]:
        start = datetime.now(timezone.utc)
        try:
            self._ensure_connection()
            if self._conn is None:
                raise RuntimeError("Postgres connection not initialized")
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return {
                "healthy": True,
                "backend": "postgres",
                "latency_ms": round(latency_ms, 2),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "healthy": False,
                "backend": "postgres",
                "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _uuid4(self):
        from uuid import uuid4

        return uuid4

    @property
    def _json(self):
        import json

        return json


def get_storage_backend(
    backend_type: str | None = None,
    **kwargs,
) -> StorageBackend:
    """Factory function to get appropriate storage backend."""
    backend_type = backend_type or os.getenv("HORDEFORGE_STORAGE_BACKEND", "json")

    if backend_type == "postgres":
        return PostgresStorageBackend(**kwargs)
    elif backend_type == "json":
        file_path = kwargs.get("file_path", ".hordeforge_data/storage.json")
        return JsonStorageBackend(file_path)
    else:
        raise ValueError(f"Unknown storage backend: {backend_type}")
