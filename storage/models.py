from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RunRecord:
    run_id: str
    pipeline_name: str
    status: str
    source: str
    correlation_id: str
    started_at: str
    tenant_id: str = "default"
    repository_full_name: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    override_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=payload["run_id"],
            tenant_id=str(payload.get("tenant_id", "default")).strip().lower() or "default",
            repository_full_name=(
                str(payload.get("repository_full_name", "")).strip().lower() or None
            ),
            pipeline_name=payload["pipeline_name"],
            status=payload["status"],
            source=payload.get("source", "unknown"),
            correlation_id=payload.get("correlation_id", ""),
            started_at=payload.get("started_at", ""),
            finished_at=payload.get("finished_at"),
            result=payload.get("result"),
            error=payload.get("error"),
            inputs=payload.get("inputs", {}) if isinstance(payload.get("inputs"), dict) else {},
            idempotency_key=payload.get("idempotency_key"),
            override_state=payload.get("override_state"),
        )


@dataclass(slots=True)
class StepLogRecord:
    run_id: str
    step_name: str
    status: str
    tenant_id: str = "default"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StepLogRecord:
        return cls(
            run_id=payload["run_id"],
            tenant_id=str(payload.get("tenant_id", "default")).strip().lower() or "default",
            step_name=payload["step_name"],
            status=payload.get("status", "UNKNOWN"),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            error=payload.get("error"),
            retry_count=int(payload.get("retry_count", 0)),
        )


@dataclass(slots=True)
class ArtifactRecord:
    run_id: str
    step_name: str
    artifact_type: str
    content: dict[str, Any]
    size_bytes: int
    tenant_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ArtifactRecord:
        content = payload.get("content", {})
        if not isinstance(content, dict):
            content = {}
        return cls(
            run_id=payload["run_id"],
            tenant_id=str(payload.get("tenant_id", "default")).strip().lower() or "default",
            step_name=payload.get("step_name", "unknown"),
            artifact_type=payload.get("artifact_type", "unknown"),
            content=content,
            size_bytes=int(payload.get("size_bytes", 0)),
        )
