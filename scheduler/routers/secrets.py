from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from cli.repo_store import (
    get_secret_value,
    list_secret_keys,
    remove_secret_value,
    set_secret_value,
)

router = APIRouter(prefix="/secrets")
logger = logging.getLogger("hordeforge.gateway")


class SecretUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


def create_secrets_router() -> APIRouter:

    @router.post("")
    async def upsert_secret(request: SecretUpsertRequest) -> dict[str, Any]:
        try:
            set_secret_value(request.name, request.value)
            return {"status": "ok", "name": request.name}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc

    @router.get("")
    async def list_secrets(name: str | None = Query(default=None)) -> dict[str, Any]:
        if name:
            value = get_secret_value(name)
            if value is None:
                return {"name": name, "value": None}
            return {"name": name, "value": "[SET]"}
        keys = list_secret_keys()
        return {"keys": keys}

    @router.delete("/{name}")
    async def delete_secret(name: str) -> dict[str, Any]:
        remove_secret_value(name)
        return {"status": "ok", "name": name}

    return router
