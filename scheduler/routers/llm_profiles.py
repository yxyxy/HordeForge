from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cli.repo_store import (
    add_or_update_llm_profile,
    get_llm_profile,
    list_llm_profiles,
    remove_llm_profile,
    set_default_llm_profile,
)

router = APIRouter(prefix="/llm")
logger = logging.getLogger("hordeforge.gateway")


class LlmProfileUpsertRequest(BaseModel):
    profile_name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    base_url: str | None = None
    api_key_ref: str | None = None
    set_default: bool = False


def create_llm_profiles_router() -> APIRouter:

    @router.post("/profiles")
    async def upsert_llm_profile(request: LlmProfileUpsertRequest) -> dict[str, Any]:
        try:
            add_or_update_llm_profile(
                profile_name=request.profile_name,
                provider=request.provider,
                model=request.model,
                base_url=request.base_url,
                api_key_ref=request.api_key_ref,
            )
            if request.set_default:
                set_default_llm_profile(request.profile_name)
            return {"status": "ok", "profile_name": request.profile_name}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc

    @router.get("/profiles")
    async def list_profiles() -> dict[str, Any]:
        profiles = list_llm_profiles()
        return {"profiles": profiles}

    @router.post("/profiles/{profile_name}/default")
    async def set_default_profile(profile_name: str) -> dict[str, Any]:
        existing = get_llm_profile(profile_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
        set_default_llm_profile(profile_name)
        return {"status": "ok", "profile_name": profile_name}

    @router.delete("/profiles/{profile_name}")
    async def delete_profile(profile_name: str) -> dict[str, Any]:
        existing = get_llm_profile(profile_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
        remove_llm_profile(profile_name)
        return {"status": "ok", "profile_name": profile_name}

    return router
