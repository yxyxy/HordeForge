from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._write_raw([])

    def _write_raw(self, payload: list[dict[str, Any]]) -> None:
        serialized = self._json.dumps(payload, ensure_ascii=False, indent=2)
        temp_path = self._file_path.with_suffix(f"{self._file_path.suffix}.{self._uuid4().hex}.tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        last_error: OSError | None = None
        for attempt in range(5):
            try:
                temp_path.replace(self._file_path)
                return
            except PermissionError as exc:
                last_error = exc
                self._time.sleep(0.01 * (attempt + 1))
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                raw = self._file_path.read_text(encoding="utf-8").strip()
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

    def write_all(self, items: list[dict[str, Any]]) -> None:
        payload = [item for item in items if isinstance(item, dict)]
        with self._lock:
            self._write_raw(payload)

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
        self._table_name = table_name
        self._conn = None
        self._ensure_connection()

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
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) NOT NULL,
                    value JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_key
                ON {self._table_name}(key);
                """
            )
            self._conn.commit()

    def read_all(self) -> list[dict[str, Any]]:
        self._ensure_connection()
        if self._conn is None:
            return []
        try:
            with self._conn.cursor() as cur:
                cur.execute(f"SELECT key, value FROM {self._table_name}")
                return [value for _, value in cur.fetchall()]
        except Exception:
            return []

    def write_all(self, items: list[dict[str, Any]]) -> None:
        self._ensure_connection()
        if self._conn is None:
            return
        try:
            with self._conn.cursor() as cur:
                # Clear existing data and insert new
                cur.execute(f"DELETE FROM {self._table_name}")
                for item in items:
                    if isinstance(item, dict):
                        cur.execute(
                            f"INSERT INTO {self._table_name} (key, value) VALUES (%s, %s)",
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
