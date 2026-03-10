from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class QueueTaskRequest:
    pipeline_name: str
    inputs: dict[str, Any]
    source: str
    correlation_id: str
    tenant_id: str = "default"
    repository_full_name: str | None = None
    idempotency_key: str | None = None


@dataclass(slots=True)
class QueueTask:
    task_id: str
    pipeline_name: str
    inputs: dict[str, Any]
    source: str
    correlation_id: str
    tenant_id: str
    repository_full_name: str | None
    idempotency_key: str | None
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "pipeline_name": self.pipeline_name,
            "inputs": self.inputs,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "repository_full_name": self.repository_full_name,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class TaskQueueBackend(ABC):
    @abstractmethod
    def enqueue(self, request: QueueTaskRequest) -> QueueTask:
        raise NotImplementedError

    @abstractmethod
    def claim_next(self, *, max_items: int = 1) -> list[QueueTask]:
        raise NotImplementedError

    @abstractmethod
    def mark_succeeded(self, task_id: str, result: dict[str, Any]) -> QueueTask:
        raise NotImplementedError

    @abstractmethod
    def mark_failed(self, task_id: str, error: str) -> QueueTask:
        raise NotImplementedError

    @abstractmethod
    def get(self, task_id: str) -> QueueTask | None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class InMemoryTaskQueue(TaskQueueBackend):
    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, QueueTask] = {}
        self._queue: deque[str] = deque()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, request: QueueTaskRequest) -> QueueTask:
        task = QueueTask(
            task_id=str(uuid4()),
            pipeline_name=request.pipeline_name,
            inputs=dict(request.inputs),
            source=request.source,
            correlation_id=request.correlation_id,
            tenant_id=str(request.tenant_id).strip().lower() or "default",
            repository_full_name=(
                str(request.repository_full_name).strip().lower()
                if request.repository_full_name
                else None
            ),
            idempotency_key=request.idempotency_key,
            status="QUEUED",
            created_at=self._utc_now_iso(),
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._queue.append(task.task_id)
        return task

    def claim_next(self, *, max_items: int = 1) -> list[QueueTask]:
        with self._lock:
            claimed: list[QueueTask] = []
            target = max(1, int(max_items))
            while self._queue and len(claimed) < target:
                task_id = self._queue.popleft()
                task = self._tasks.get(task_id)
                if task is None or task.status != "QUEUED":
                    continue
                task.status = "RUNNING"
                task.started_at = self._utc_now_iso()
                claimed.append(task)
            return list(claimed)

    def mark_succeeded(self, task_id: str, result: dict[str, Any]) -> QueueTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Queue task not found: {task_id}")
            task.status = "SUCCEEDED"
            task.finished_at = self._utc_now_iso()
            task.result = dict(result)
            task.error = None
            return task

    def mark_failed(self, task_id: str, error: str) -> QueueTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Queue task not found: {task_id}")
            task.status = "FAILED"
            task.finished_at = self._utc_now_iso()
            task.error = str(error)
            return task

    def get(self, task_id: str) -> QueueTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._queue.clear()


class ExternalBrokerQueueAdapter(TaskQueueBackend):
    def __init__(self, *, broker_url: str) -> None:
        self.broker_url = str(broker_url).strip()

    @staticmethod
    def _unsupported() -> NotImplementedError:
        return NotImplementedError(
            "External broker adapter is a placeholder. Implement vendor-specific transport."
        )

    def enqueue(self, request: QueueTaskRequest) -> QueueTask:
        raise self._unsupported()

    def claim_next(self, *, max_items: int = 1) -> list[QueueTask]:
        raise self._unsupported()

    def mark_succeeded(self, task_id: str, result: dict[str, Any]) -> QueueTask:
        raise self._unsupported()

    def mark_failed(self, task_id: str, error: str) -> QueueTask:
        raise self._unsupported()

    def get(self, task_id: str) -> QueueTask | None:
        raise self._unsupported()

    def clear(self) -> None:
        raise self._unsupported()
