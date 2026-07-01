from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from hordeforge_config import RunConfig
from observability.alerts import AlertDispatcher
from observability.metrics import RuntimeMetrics
from orchestrator import OrchestratorEngine
from scheduler.idempotency import IdempotencyStore
from scheduler.queue_backends import get_task_queue_backend
from scheduler.task_queue import InMemoryTaskQueue
from scheduler.tenant_registry import TenantRepositoryRegistry
from storage.repositories.artifact_repository import ArtifactRepository
from storage.repositories.run_repository import RunRepository
from storage.repositories.step_log_repository import StepLogRepository

logger = logging.getLogger("hordeforge.gateway")


class GatewayState:
    """Encapsulates all mutable gateway state for testability and clarity."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.container_started_at = datetime.now(timezone.utc)

        self.engine = OrchestratorEngine(
            pipelines_dir=config.pipelines_dir,
            rules_dir=config.rules_dir,
            rule_set_version=config.rule_set_version,
            max_parallel_workers=config.max_parallel_workers,
            strict_schema_validation=config.strict_schema_validation,
            enable_dynamic_fallback=config.enable_dynamic_fallback,
        )

        self.runs: dict[str, dict[str, Any]] = {}
        self.run_repository = RunRepository(storage_dir=config.storage_dir)
        self.step_log_repository = StepLogRepository(storage_dir=config.storage_dir)
        self.artifact_repository = ArtifactRepository(storage_dir=config.storage_dir)
        self.idempotency_store = IdempotencyStore(ttl_seconds=config.idempotency_ttl_seconds)
        self.run_runtime_inputs: dict[str, dict[str, Any]] = {}
        self._runs_max_age_seconds = 3600
        self._runs_last_cleanup = time.time()

        self.metrics = RuntimeMetrics()
        self.alert_dispatcher = AlertDispatcher(throttle_seconds=60)

        self.cron_dispatcher = None

        self.queue_backend_requested = config.queue_backend
        self.queue_backend_active: str | None = None
        self.queue_backend_error: str | None = None
        self.queue_autodrain_thread: threading.Thread | None = None
        self.queue_autodrain_stop = threading.Event()

        self.task_queue = self._init_task_queue()
        self.tenant_registry = TenantRepositoryRegistry(
            mapping=config.tenant_repository_map,
            default_tenant_id=config.default_tenant_id,
            enforce_boundaries=config.enforce_tenant_boundaries,
        )
        self.storage_backend_requested = os.getenv("HORDEFORGE_STORAGE_BACKEND", "json")
        self.storage_backend_error: str | None = None

        self._validate_backends_on_startup()

    def _init_task_queue(self) -> InMemoryTaskQueue:
        backend_type = self.queue_backend_requested or "memory"
        try:
            queue = get_task_queue_backend(backend_type)
            self.queue_backend_active = backend_type
            return queue  # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            self.queue_backend_active = "memory"
            self.queue_backend_error = str(exc)
            logger.warning(
                "Queue backend '%s' failed to initialize: %s. Falling back to memory.",
                backend_type,
                exc,
            )
            return InMemoryTaskQueue()

    def _validate_backends_on_startup(self) -> None:
        if self.storage_backend_requested == "postgres":
            try:
                store = self.run_repository.store
                if hasattr(store, "health_check"):
                    health = store.health_check()
                    if isinstance(health, dict) and not health.get("healthy", True):
                        self.storage_backend_error = str(health.get("error", "unhealthy"))
                        logger.warning(
                            "Postgres storage health check failed: %s",
                            self.storage_backend_error,
                        )
                else:
                    store.read_all()
            except Exception as exc:  # noqa: BLE001
                self.storage_backend_error = str(exc)
                logger.warning("Postgres storage health check failed: %s", exc)

        if self.queue_backend_requested == "redis":
            if self.queue_backend_error:
                logger.warning(
                    "Redis queue backend failed to initialize: %s",
                    self.queue_backend_error,
                )
                return
            if hasattr(self.task_queue, "health_check"):
                try:
                    health = self.task_queue.health_check()
                    if isinstance(health, dict) and not health.get("healthy", True):
                        self.queue_backend_error = str(health.get("error", "unhealthy"))
                        logger.warning(
                            "Redis queue backend health check failed: %s",
                            self.queue_backend_error,
                        )
                except Exception as exc:  # noqa: BLE001
                    self.queue_backend_error = str(exc)
                    logger.warning("Redis queue backend health check failed: %s", exc)

    def cleanup_old_runs(self) -> None:
        now = time.time()
        if now - self._runs_last_cleanup < 300:
            return
        self._runs_last_cleanup = now
        expired = [
            k
            for k, v in self.runs.items()
            if now - v.get("_created_at", now) > self._runs_max_age_seconds
        ]
        for k in expired:
            self.runs.pop(k, None)
            self.run_runtime_inputs.pop(k, None)

    def remember_runtime_inputs(self, run_id: str, inputs: dict[str, Any]) -> None:
        self.run_runtime_inputs[run_id] = dict(inputs if isinstance(inputs, dict) else {})

    def resolve_runtime_inputs(self, record: Any) -> dict[str, Any]:
        runtime_inputs = self.run_runtime_inputs.get(record.run_id)
        if isinstance(runtime_inputs, dict):
            return dict(runtime_inputs)
        return dict(record.inputs) if isinstance(record.inputs, dict) else {}
