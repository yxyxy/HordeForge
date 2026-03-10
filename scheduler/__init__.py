"""Scheduler package for HordeForge gateway, cron, and idempotency primitives."""

from scheduler.cron_dispatcher import CronDispatcher
from scheduler.cron_runtime import build_default_cron_dispatcher, build_default_job_handlers
from scheduler.idempotency import IdempotencyStore, build_idempotency_key
from scheduler.schedule_registry import (
    ScheduleRegistry,
    ScheduleSpec,
    build_default_schedule_registry,
)
from scheduler.task_queue import (
    ExternalBrokerQueueAdapter,
    InMemoryTaskQueue,
    QueueTask,
    QueueTaskRequest,
    TaskQueueBackend,
)

__all__ = [
    "CronDispatcher",
    "build_default_cron_dispatcher",
    "build_default_job_handlers",
    "ScheduleRegistry",
    "ScheduleSpec",
    "build_default_schedule_registry",
    "IdempotencyStore",
    "build_idempotency_key",
    "TaskQueueBackend",
    "QueueTaskRequest",
    "QueueTask",
    "InMemoryTaskQueue",
    "ExternalBrokerQueueAdapter",
]
