from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("hordeforge.gateway")


def create_health_router(state: Any) -> APIRouter:
    """Create health check routes bound to gateway state."""

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": time.time(),
            "version": "0.1.0",
        }

    @router.get("/health/redis")
    async def health_redis() -> dict[str, Any]:
        queue = state.task_queue
        if not hasattr(queue, "health_check"):
            return {"status": "unavailable", "backend": state.queue_backend_active}
        try:
            health = queue.health_check()
            return {
                "status": "healthy" if health.get("healthy", True) else "unhealthy",
                "backend": state.queue_backend_active,
                "details": health,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "backend": state.queue_backend_active,
                "error": str(exc)[:300],
            }

    @router.get("/health/postgres")
    async def health_postgres() -> dict[str, Any]:
        store = state.run_repository.store
        if not hasattr(store, "health_check"):
            return {"status": "unavailable", "backend": state.storage_backend_requested}
        try:
            health = store.health_check()
            return {
                "status": "healthy" if health.get("healthy", True) else "unhealthy",
                "backend": state.storage_backend_requested,
                "details": health,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "backend": state.storage_backend_requested,
                "error": str(exc)[:300],
            }

    @router.get("/ready")
    async def ready() -> dict[str, Any]:
        checks: dict[str, str] = {}
        if state.storage_backend_error:
            checks["storage"] = state.storage_backend_error
        if state.queue_backend_error:
            checks["queue"] = state.queue_backend_error
        if checks:
            return {"status": "not_ready", "checks": checks}
        return {"status": "ready"}

    return router
