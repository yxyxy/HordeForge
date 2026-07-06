from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()
logger = logging.getLogger("hordeforge.gateway")


def create_metrics_router(state: Any) -> APIRouter:

    @router.get("/metrics")
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(state.metrics.render_prometheus(), media_type="text/plain")

    @router.post("/metrics/export")
    async def export_metrics() -> dict[str, Any]:
        return {"status": "ok", "exported": True}

    return router
