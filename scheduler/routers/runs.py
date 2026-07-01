from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from logging_utils import redact_sensitive_data

router = APIRouter(prefix="/runs")
logger = logging.getLogger("hordeforge.gateway")


class OverrideCommand(BaseModel):
    action: str = Field(..., min_length=1)
    reason: str = Field(default="")


def create_runs_router(state: Any) -> APIRouter:

    @router.get("")
    async def list_runs() -> dict[str, Any]:
        state.cleanup_old_runs()
        records = state.run_repository.list()
        items = []
        for record in records:
            items.append(
                {
                    "run_id": record.run_id,
                    "pipeline_name": record.pipeline_name,
                    "status": record.status,
                    "created_at": record.started_at,
                    "finished_at": record.finished_at,
                    "tenant_id": record.tenant_id,
                }
            )
        return {"runs": items}

    @router.get("/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        state.cleanup_old_runs()
        record = state.run_repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        result = redact_sensitive_data(record.result) if isinstance(record.result, dict) else {}
        run_state = state.runs.get(run_id, {})
        return {
            "run_id": record.run_id,
            "pipeline_name": record.pipeline_name,
            "status": record.status,
            "created_at": record.created_at,
            "finished_at": record.finished_at,
            "result": result,
            "run_state": run_state,
        }

    @router.post("/{run_id}/override")
    async def override_run(run_id: str, command: OverrideCommand) -> dict[str, Any]:
        from orchestrator.override import RUN_OVERRIDE_REGISTRY

        state.cleanup_old_runs()
        record = state.run_repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        RUN_OVERRIDE_REGISTRY.register(run_id, command.action, command.reason)
        return {
            "status": "ok",
            "run_id": run_id,
            "action": command.action,
            "reason": command.reason,
        }

    return router
