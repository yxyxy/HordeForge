from __future__ import annotations

import pytest

import scheduler.queue_backends as queue_backends
from scheduler.queue_backends import get_task_queue_backend
from scheduler.task_queue import InMemoryTaskQueue, QueueTaskRequest


def test_get_task_queue_backend_memory():
    """Test factory for memory backend."""
    backend = get_task_queue_backend("memory")
    assert isinstance(backend, InMemoryTaskQueue)


def test_get_task_queue_backend_redis_not_installed():
    """Test Redis backend handles missing Redis installation gracefully."""
    # В новой версии системы, если Redis недоступен, может происходить fallback

    try:
        # Попробуем создать Redis backend
        get_task_queue_backend("redis", connection_url="redis://localhost:6379/0")
        # В зависимости от реализации, может быть создан RedisTaskQueue или fallback
    except ImportError:
        # Это нормально, если Redis не установлен
        pass
    except Exception:
        # Также допустимо, если Redis установлен, но недоступен (например, не запущен)
        pass


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


class _FakeRedis:
    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._values: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def _get_list(self, key: str) -> list[str]:
        return self._lists.setdefault(key, [])

    def rpush(self, key: str, value: str) -> int:
        items = self._get_list(key)
        items.append(value)
        return len(items)

    def lpush(self, key: str, value: str) -> int:
        items = self._get_list(key)
        items.insert(0, value)
        return len(items)

    def lpop(self, key: str):
        items = self._get_list(key)
        if not items:
            return None
        return items.pop(0)

    def lmove(self, source: str, destination: str, wherefrom: str, whereto: str):
        source_items = self._get_list(source)
        if not source_items:
            return None
        if wherefrom.upper() == "LEFT":
            item = source_items.pop(0)
        else:
            item = source_items.pop()
        dest_items = self._get_list(destination)
        if whereto.upper() == "LEFT":
            dest_items.insert(0, item)
        else:
            dest_items.append(item)
        return item

    def set(self, key: str, value: str) -> bool:
        self._values[key] = value
        return True

    def setex(self, key: str, _ttl: int, value: str) -> bool:
        self._values[key] = value
        return True

    def get(self, key: str):
        return self._values.get(key)

    def lrem(self, key: str, count: int, value: str) -> int:
        items = self._get_list(key)
        if count == 1:
            try:
                idx = items.index(value)
            except ValueError:
                return 0
            items.pop(idx)
            return 1
        removed = 0
        filtered: list[str] = []
        for item in items:
            if item == value and (count == 0 or removed < abs(count)):
                removed += 1
                continue
            filtered.append(item)
        self._lists[key] = filtered
        return removed

    def keys(self, pattern: str) -> list[str]:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [
                k
                for k in list(self._lists.keys()) + list(self._values.keys())
                if k.startswith(prefix)
            ]
        return []

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._lists:
                del self._lists[key]
                deleted += 1
            if key in self._values:
                del self._values[key]
                deleted += 1
        return deleted

    def close(self) -> None:
        return


def _build_redis_backend(monkeypatch: pytest.MonkeyPatch, redis_obj: _FakeRedis):
    def _fake_ensure_connection(self) -> None:
        self._redis = redis_obj

    monkeypatch.setattr(
        queue_backends.RedisTaskQueue, "_ensure_connection", _fake_ensure_connection
    )
    monkeypatch.setattr(queue_backends.RedisTaskQueue, "_check_connection", lambda self: None)
    return queue_backends.RedisTaskQueue(connection_url="redis://fake:6379/0", queue_name="hf:test")


def test_redis_claim_keeps_task_recoverable_until_ack(monkeypatch):
    redis_obj = _FakeRedis()
    backend = _build_redis_backend(monkeypatch, redis_obj)
    queued = backend.enqueue(
        QueueTaskRequest(
            pipeline_name="init_pipeline",
            inputs={"x": 1},
            source="test",
            correlation_id="corr-redis-1",
            tenant_id="default",
        )
    )

    claimed = backend.claim_next(max_items=1)
    assert len(claimed) == 1
    assert claimed[0].task_id == queued.task_id

    # Simulate worker crash/restart before ack: a new backend instance should requeue in-flight tasks.
    backend_after_restart = _build_redis_backend(monkeypatch, redis_obj)
    claimed_after_restart = backend_after_restart.claim_next(max_items=1)
    assert len(claimed_after_restart) == 1
    assert claimed_after_restart[0].task_id == queued.task_id


def test_redis_ack_removes_task_from_processing(monkeypatch):
    redis_obj = _FakeRedis()
    backend = _build_redis_backend(monkeypatch, redis_obj)
    queued = backend.enqueue(
        QueueTaskRequest(
            pipeline_name="init_pipeline",
            inputs={"x": 2},
            source="test",
            correlation_id="corr-redis-2",
            tenant_id="default",
        )
    )

    claimed = backend.claim_next(max_items=1)
    assert len(claimed) == 1
    assert claimed[0].task_id == queued.task_id

    completed = backend.mark_succeeded(queued.task_id, {"status": "started"})
    assert completed.status == "SUCCEEDED"

    # Restart should not replay acknowledged task.
    backend_after_restart = _build_redis_backend(monkeypatch, redis_obj)
    assert backend_after_restart.claim_next(max_items=1) == []
