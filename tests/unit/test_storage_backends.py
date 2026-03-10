from __future__ import annotations

import os
import tempfile

import pytest

from storage.backends import JsonStorageBackend, get_storage_backend


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
