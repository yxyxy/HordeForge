from __future__ import annotations

import pytest

from scheduler.queue_backends import get_task_queue_backend
from scheduler.task_queue import InMemoryTaskQueue


def test_get_task_queue_backend_memory():
    """Test factory for memory backend."""
    backend = get_task_queue_backend("memory")
    assert isinstance(backend, InMemoryTaskQueue)


def test_get_task_queue_backend_redis_not_installed():
    """Test Redis backend raises import error when redis not installed."""
    import sys

    import scheduler.queue_backends as queue_backends

    # Save original modules
    original_redis = sys.modules.get("redis")
    original_redis_connection_pool = sys.modules.get("redis.connection")

    # Remove redis from modules to simulate not installed
    if "redis" in sys.modules:
        del sys.modules["redis"]
    if "redis.connection" in sys.modules:
        del sys.modules["redis.connection"]

    # Also remove from queue_backends to force re-import
    if hasattr(queue_backends, "RedisTaskQueue"):
        # Force reimport by removing the reference
        pass

    try:
        with pytest.raises(ImportError, match="redis is required"):
            get_task_queue_backend("redis", connection_url="redis://localhost:6379/0")
    finally:
        # Restore original modules
        if original_redis is not None:
            sys.modules["redis"] = original_redis
        if original_redis_connection_pool is not None:
            sys.modules["redis.connection"] = original_redis_connection_pool


def test_get_task_queue_backend_unknown():
    """Test factory rejects unknown backend."""
    with pytest.raises(ValueError, match="Unknown queue backend"):
        get_task_queue_backend("unknown_backend")


def test_get_task_queue_backend_default_is_memory():
    """Test default backend is memory."""
    backend = get_task_queue_backend(None)
    assert isinstance(backend, InMemoryTaskQueue)


def test_get_task_queue_backend_uses_env_memory(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_QUEUE_BACKEND", "memory")
    backend = get_task_queue_backend()
    assert isinstance(backend, InMemoryTaskQueue)


def test_get_task_queue_backend_uses_env_redis(monkeypatch):
    import scheduler.queue_backends as queue_backends

    class DummyRedis(queue_backends.TaskQueueBackend):
        def enqueue(self, request):
            raise NotImplementedError

        def claim_next(self, *, max_items: int = 1):
            return []

        def mark_succeeded(self, task_id: str, result: dict):
            raise NotImplementedError

        def mark_failed(self, task_id: str, error: str):
            raise NotImplementedError

        def get(self, task_id: str):
            return None

        def clear(self) -> None:
            pass

    monkeypatch.setenv("HORDEFORGE_QUEUE_BACKEND", "redis")
    monkeypatch.setattr(queue_backends, "RedisTaskQueue", DummyRedis)

    backend = get_task_queue_backend()
    assert isinstance(backend, DummyRedis)
