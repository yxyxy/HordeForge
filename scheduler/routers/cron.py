from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/cron")
logger = logging.getLogger("hordeforge.gateway")


class CronManualTriggerRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


def create_cron_router(state: Any) -> APIRouter:

    @router.get("/jobs")
    async def list_cron_jobs() -> dict[str, Any]:
        if state.cron_dispatcher is None:
            return {"jobs": [], "message": "Cron dispatcher not initialized"}
        jobs = state.cron_dispatcher.list_jobs()
        return {"jobs": jobs}

    @router.post("/run-due")
    async def run_due_jobs() -> dict[str, Any]:
        if state.cron_dispatcher is None:
            return {"status": "skipped", "message": "Cron dispatcher not initialized"}
        results = state.cron_dispatcher.run_due_jobs()
        return {"status": "ok", "results": results}

    @router.post("/jobs/{job_name}/trigger")
    async def trigger_job(job_name: str, request: CronManualTriggerRequest) -> dict[str, Any]:
        if state.cron_dispatcher is None:
            raise HTTPException(status_code=503, detail="Cron dispatcher not initialized")
        result = state.cron_dispatcher.trigger_job(job_name, payload=request.payload)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
        return {"status": "ok", "job_name": job_name, "result": result}

    return router
