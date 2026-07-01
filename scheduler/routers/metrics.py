from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()
logger = logging.getLogger("hordeforge.gateway")


def create_metrics_router(state: Any) -> APIRouter:

    @router.get("/metrics")
    async def metrics() -> PlainTextResponse:
        lines = [
            "# HELP hordeforge_runs_total Total pipeline runs",
            "# TYPE hordeforge_runs_total counter",
            f"hordeforge_runs_total {state.metrics.total_runs}",
            "# HELP hordeforge_runs_failed_total Failed pipeline runs",
            "# TYPE hordeforge_runs_failed_total counter",
            f"hordeforge_runs_failed_total {state.metrics.failed_runs}",
            "# HELP hordeforge_uptime_seconds Gateway uptime in seconds",
            "# TYPE hordeforge_uptime_seconds gauge",
            f"hordeforge_uptime_seconds {time.time() - state.container_started_at.timestamp()}",
        ]
        return PlainTextResponse("\n".join(lines), media_type="text/plain")

    @router.post("/metrics/export")
    async def export_metrics() -> dict[str, Any]:
        return {"status": "ok", "exported": True}

    return router
