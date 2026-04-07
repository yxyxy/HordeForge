from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from storage.backends import (
    JsonStorageBackend,
    archive_and_prune_rotated_logs,
    get_storage_backend,
    rotate_current_log_files,
)


def test_json_storage_backend_read_write():
    """Test JSON storage backend basic read/write operations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_file = os.path.join(tmp_dir, "test_storage.json")
        backend = JsonStorageBackend(storage_file)

        # Initial read should be empty
        assert backend.read_all() == []

        # Write some data
        items = [
            {"run_id": "run-1", "status": "SUCCESS"},
            {"run_id": "run-2", "status": "FAILED"},
        ]
        backend.write_all(items)

        # Read back
        result = backend.read_all()
        assert len(result) == 2
        assert result[0]["run_id"] == "run-1"
        assert result[1]["run_id"] == "run-2"

        backend.close()


def test_json_storage_backend_overwrite():
    """Test JSON storage backend overwrites correctly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_file = os.path.join(tmp_dir, "test_overwrite.json")
        backend = JsonStorageBackend(storage_file)

        backend.write_all([{"run_id": "run-1", "status": "SUCCESS"}])
        backend.write_all([{"run_id": "run-2", "status": "FAILED"}])

        result = backend.read_all()
        assert len(result) == 1
        assert result[0]["run_id"] == "run-2"

        backend.close()


def test_json_storage_backend_filters_invalid():
    """Test JSON storage backend filters invalid items."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_file = os.path.join(tmp_dir, "test_filter.json")
        backend = JsonStorageBackend(storage_file)

        items = [
            {"run_id": "run-1", "status": "SUCCESS"},
            "not a dict",
            None,
            {"run_id": "run-2", "status": "FAILED"},
        ]
        backend.write_all(items)  # type: ignore

        result = backend.read_all()
        assert len(result) == 2

        backend.close()


def test_get_storage_backend_json():
    """Test factory for JSON backend."""
    backend = get_storage_backend("json", file_path=".hordeforge_data/test.json")
    assert isinstance(backend, JsonStorageBackend)
    backend.close()


def test_get_storage_backend_unknown():
    """Test factory rejects unknown backend."""
    with pytest.raises(ValueError, match="Unknown storage backend"):
        get_storage_backend("unknown_backend")


def test_get_storage_backend_uses_env_json(monkeypatch):
    """Factory should respect HORDEFORGE_STORAGE_BACKEND env var."""
    monkeypatch.setenv("HORDEFORGE_STORAGE_BACKEND", "json")
    backend = get_storage_backend()
    assert isinstance(backend, JsonStorageBackend)
    backend.close()


def test_get_storage_backend_uses_env_postgres(monkeypatch):
    """Factory should respect HORDEFORGE_STORAGE_BACKEND=postgres."""
    import storage.backends as storage_backends

    class DummyBackend(storage_backends.StorageBackend):
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def read_all(self):
            return []

        def write_all(self, items):
            self.items = items

        def close(self):
            pass

    monkeypatch.setenv("HORDEFORGE_STORAGE_BACKEND", "postgres")
    monkeypatch.setattr(storage_backends, "PostgresStorageBackend", DummyBackend)

    backend = get_storage_backend()
    assert isinstance(backend, DummyBackend)
    backend.close()


def test_json_storage_backend_splits_large_payload_into_parts_and_reads_all():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_file = Path(tmp_dir) / "logs" / "current" / "runs.json"
        backend = JsonStorageBackend(storage_file)

        items = [{"run_id": f"r-{idx}", "payload": "x" * 8000} for idx in range(250)]
        backend.write_all(items)

        part_files = sorted(storage_file.parent.glob("runs.json.part-*"))
        assert part_files

        loaded = backend.read_all()
        assert len(loaded) == len(items)
        assert loaded[0]["run_id"] == "r-0"
        assert loaded[-1]["run_id"] == f"r-{len(items) - 1}"

        backend.close()


def test_rotate_current_log_files_moves_current_files_with_start_timestamp_prefix():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        current_dir = storage_dir / "logs" / "current"
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "runs.json").write_text("[]", encoding="utf-8")
        (current_dir / "runs.json.part-001").write_text("[]", encoding="utf-8")
        (current_dir / "step_logs.json").write_text("[]", encoding="utf-8")

        started_at = datetime(2026, 4, 4, 10, 15, 33, tzinfo=timezone.utc)
        rotated = rotate_current_log_files(storage_dir=storage_dir, container_started_at=started_at)

        rotated_names = {path.name for path in rotated}
        assert "2026-04-04T10-15-33Z__runs.json" in rotated_names
        assert "2026-04-04T10-15-33Z__runs.json.part-001" in rotated_names
        assert "2026-04-04T10-15-33Z__step_logs.json" in rotated_names
        assert not (current_dir / "runs.json").exists()


def test_archive_and_prune_rotated_logs_compresses_and_removes_by_retention():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        logs_dir = storage_dir / "logs"
        archive_dir = logs_dir / "archive"
        logs_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

        old_rotated = logs_dir / "2026-03-20T10-15-33Z__runs.json"
        old_rotated.write_text("[]", encoding="utf-8")
        old_epoch = (datetime(2026, 4, 4, tzinfo=timezone.utc) - timedelta(days=8)).timestamp()
        os.utime(old_rotated, (old_epoch, old_epoch))

        old_archive = archive_dir / "old.gz"
        old_archive.write_bytes(b"archive")
        os.utime(old_archive, (old_epoch, old_epoch))

        result = archive_and_prune_rotated_logs(
            storage_dir=storage_dir,
            now=datetime(2026, 4, 4, tzinfo=timezone.utc),
            archive_after_days=7,
            retention_days=7,
        )

        assert result["compressed"] == 1
        assert result["deleted_archives"] == 1
        assert (archive_dir / "2026-03-20T10-15-33Z__runs.json.gz").exists()
        assert not old_rotated.exists()
        assert not old_archive.exists()
