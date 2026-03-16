from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from scheduler.task_queue import QueueTaskRequest, TaskQueueBackend

if TYPE_CHECKING:
    from scheduler.task_queue import QueueTask

logger = logging.getLogger(__name__)


class RedisTaskQueue(TaskQueueBackend):
    """Redis-backed task queue for production use with connection pooling."""

    def __init__(
        self,
        *,
        connection_url: str | None = None,
        queue_name: str = "hordeforge:tasks",
        result_ttl_seconds: int = 86400,
        pool_size: int = 10,
        pool_max_overflow: int = 20,
        pool_timeout: int = 30,
        health_check_interval: int = 60,
    ) -> None:
        self._connection_url = connection_url or os.getenv(
            "HORDEFORGE_REDIS_URL", "redis://localhost:6379/0"
        )
        self._queue_name = queue_name
        self._result_ttl_seconds = result_ttl_seconds
        self._pool_size = pool_size
        self._pool_max_overflow = pool_max_overflow
        self._pool_timeout = pool_timeout
        self._health_check_interval = health_check_interval
        self._redis = None
        self._last_health_check: datetime | None = None
        self._ensure_connection()

    def _ensure_connection(self) -> None:
        if self._redis is not None:
            return
        try:
            import redis
            from redis import ConnectionPool

            # Create connection pool for better performance
            self._connection_pool = ConnectionPool.from_url(
                self._connection_url,
                max_connections=self._pool_size + self._pool_max_overflow,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=True,
                health_check_interval=self._health_check_interval,
            )
            self._redis = redis.Redis(
                connection_pool=self._connection_pool,
                socket_timeout=self._pool_timeout,
            )
            self._redis.ping()
            logger.info("Redis connection established with pool size %d", self._pool_size)
        except ImportError as e:
            raise ImportError(
                "redis is required for Redis queue. Install with: pip install redis"
            ) from e
        except Exception as exc:
            message = str(exc).lower()
            if "connection refused" in message or "error 10061" in message:
                raise ImportError(
                    "redis is required for Redis queue. Install with: pip install redis"
                ) from exc
            raise RuntimeError(f"Failed to connect to Redis: {exc}") from exc

    def health_check(self) -> dict[str, Any]:
        """Perform health check on Redis connection."""
        try:
            self._ensure_connection()
            start = datetime.now(timezone.utc)
            pong = self._redis.ping()
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            # Get pool stats
            pool_info = {}
            if hasattr(self, "_connection_pool"):
                try:
                    pool_info = {
                        "pool_size": self._pool_size,
                        "pool_max_overflow": self._pool_max_overflow,
                    }
                except Exception:  # noqa: BLE001
                    pass

            return {
                "healthy": pong,
                "status": "healthy" if pong else "unhealthy",
                "backend": "redis",
                "latency_ms": round(latency_ms, 2),
                "pool": pool_info,
                "checked_at": self._utc_now_iso(),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "healthy": False,
                "status": "unhealthy",
                "backend": "redis",
                "error": str(exc),
                "checked_at": self._utc_now_iso(),
            }

    def _check_connection(self) -> None:
        """Check connection health before each operation."""
        now = datetime.now(timezone.utc)
        if (
            self._last_health_check is None
            or (now - self._last_health_check).total_seconds() > self._health_check_interval
        ):
            health = self.health_check()
            if not health.get("healthy", False):
                # Try to reconnect
                self._redis = None
                self._ensure_connection()
            self._last_health_check = now

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, request: QueueTaskRequest) -> QueueTask:
        # Import at runtime to avoid circular dependency
        from scheduler.task_queue import QueueTask  # noqa: E402

        self._ensure_connection()
        self._check_connection()
        task_id = str(uuid4())
        task = QueueTask(
            task_id=task_id,
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
        task_dict = task.to_dict()
        # Use sorted JSON for consistent hashing
        task_json = json.dumps(task_dict, sort_keys=True, ensure_ascii=False)
        self._redis.rpush(self._queue_name, task_json)
        return task

    def claim_next(self, *, max_items: int = 1) -> list[QueueTask]:
        from scheduler.task_queue import QueueTask  # noqa: E402

        self._ensure_connection()
        self._check_connection()
        claimed: list[QueueTask] = []
        target = max(1, int(max_items))

        for _ in range(target):
            # Atomic pop from left (blocking would require BLPOP)
            task_json = self._redis.lpop(self._queue_name)
            if task_json is None:
                break
            try:
                data = json.loads(task_json)
                task = QueueTask(
                    task_id=data["task_id"],
                    pipeline_name=data["pipeline_name"],
                    inputs=data["inputs"],
                    source=data["source"],
                    correlation_id=data["correlation_id"],
                    tenant_id=data["tenant_id"],
                    repository_full_name=data.get("repository_full_name"),
                    idempotency_key=data.get("idempotency_key"),
                    status="RUNNING",
                    created_at=data["created_at"],
                    started_at=self._utc_now_iso(),
                )
                claimed.append(task)
            except (json.JSONDecodeError, KeyError):
                continue

        return claimed

    def mark_succeeded(self, task_id: str, result: dict[str, Any]) -> QueueTask:
        from scheduler.task_queue import QueueTask  # noqa: E402

        self._ensure_connection()
        self._check_connection()
        key = f"{self._queue_name}:result:{task_id}"
        result_json = json.dumps(result, ensure_ascii=False)
        self._redis.setex(key, self._result_ttl_seconds, result_json)

        # Update status in a separate set for tracking
        status_key = f"{self._queue_name}:status:{task_id}"
        status_data = json.dumps(
            {
                "status": "SUCCEEDED",
                "finished_at": self._utc_now_iso(),
                "result": result,
            },
            ensure_ascii=False,
        )
        self._redis.setex(status_key, self._result_ttl_seconds, status_data)

        # Return a minimal task for compatibility
        return QueueTask(
            task_id=task_id,
            pipeline_name="",
            inputs={},
            source="",
            correlation_id="",
            tenant_id="default",
            repository_full_name=None,
            idempotency_key=None,
            status="SUCCEEDED",
            created_at="",
            finished_at=self._utc_now_iso(),
            result=result,
        )

    def mark_failed(self, task_id: str, error: str) -> QueueTask:
        from scheduler.task_queue import QueueTask  # noqa: E402

        self._ensure_connection()
        self._check_connection()
        status_key = f"{self._queue_name}:status:{task_id}"
        status_data = json.dumps(
            {
                "status": "FAILED",
                "finished_at": self._utc_now_iso(),
                "error": error,
            },
            ensure_ascii=False,
        )
        self._redis.setex(status_key, self._result_ttl_seconds, status_data)

        return QueueTask(
            task_id=task_id,
            pipeline_name="",
            inputs={},
            source="",
            correlation_id="",
            tenant_id="default",
            repository_full_name=None,
            idempotency_key=None,
            status="FAILED",
            created_at="",
            finished_at=self._utc_now_iso(),
            error=error,
        )

    def get(self, task_id: str) -> QueueTask | None:
        from scheduler.task_queue import QueueTask  # noqa: E402

        self._ensure_connection()
        self._check_connection()
        status_key = f"{self._queue_name}:status:{task_id}"
        status_json = self._redis.get(status_key)
        if status_json is None:
            return None
        try:
            data = json.loads(status_json)
            return QueueTask(
                task_id=task_id,
                pipeline_name="",
                inputs={},
                source="",
                correlation_id="",
                tenant_id="default",
                repository_full_name=None,
                idempotency_key=None,
                status=data.get("status", "UNKNOWN"),
                created_at="",
                started_at=data.get("started_at"),
                finished_at=data.get("finished_at"),
                result=data.get("result"),
                error=data.get("error"),
            )
        except json.JSONDecodeError:
            return None

    def clear(self) -> None:
        self._ensure_connection()
        self._check_connection()
        # Clear queue and status keys
        keys = self._redis.keys(f"{self._queue_name}:*")
        if keys:
            self._redis.delete(*keys)
        # Clear list
        self._redis.delete(self._queue_name)

    def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis is not None:
            self._redis.close()
            if hasattr(self, "_connection_pool"):
                self._connection_pool.disconnect()
            self._redis = None
            logger.info("Redis connection closed")


def get_task_queue_backend(backend_type: str | None = None, **kwargs) -> TaskQueueBackend:
    """Factory function to get appropriate task queue backend."""
    from scheduler.task_queue import InMemoryTaskQueue

    backend_type = backend_type or os.getenv("HORDEFORGE_QUEUE_BACKEND", "memory")

    if backend_type == "redis":
        return RedisTaskQueue(**kwargs)
    elif backend_type == "memory":
        return InMemoryTaskQueue()
    else:
        raise ValueError(f"Unknown queue backend: {backend_type}")
