from __future__ import annotations

from typing import Any


def build_agent_result(
    *,
    status: str,
    artifact_type: str,
    artifact_content: dict[str, Any],
    reason: str,
    confidence: float,
    logs: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": artifact_content}],
        "decisions": [{"reason": reason, "confidence": confidence}],
        "logs": list(logs or []),
        "next_actions": list(next_actions or []),
    }


def get_artifact_from_result(result: Any, artifact_type: str) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("type") == artifact_type and isinstance(artifact.get("content"), dict):
            return artifact["content"]
    return None


def get_artifact_from_context(
    context: dict[str, Any],
    artifact_type: str,
    *,
    preferred_steps: list[str] | None = None,
) -> dict[str, Any] | None:
    direct = context.get(artifact_type)
    if isinstance(direct, dict):
        return direct

    ordered_steps = list(preferred_steps or [])
    for key in context.keys():
        if key not in ordered_steps:
            ordered_steps.append(key)

    for step_name in ordered_steps:
        step_result = context.get(step_name)
        artifact = get_artifact_from_result(step_result, artifact_type)
        if artifact is not None:
            return artifact
    return None


def get_step_status(context: dict[str, Any], step_name: str) -> str:
    step_result = context.get(step_name)
    if isinstance(step_result, dict):
        raw_status = step_result.get("status")
        if isinstance(raw_status, str) and raw_status:
            return raw_status
    return "MISSING"
