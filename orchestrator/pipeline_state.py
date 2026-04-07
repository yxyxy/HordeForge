from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PipelineState(BaseModel):
    """Typed runtime state used by orchestrator boundaries."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    pipeline_name: str = Field(min_length=1)
    current_step: str | None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    pending_steps: list[str] = Field(default_factory=list)
    failed_steps: list[str] = Field(default_factory=list)
    locks: list[str] = Field(default_factory=list)
    retry_state: dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_legacy_state(
        cls,
        *,
        run_id: str,
        pipeline_name: str,
        legacy_state: dict[str, Any] | None,
    ) -> PipelineState:
        return cls(
            run_id=run_id,
            pipeline_name=pipeline_name,
            current_step=None,
            artifacts=dict(legacy_state or {}),
        )
