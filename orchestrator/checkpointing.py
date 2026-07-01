from __future__ import annotations

from threading import RLock
from typing import Any

from orchestrator.context import ExecutionContext
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator, SchemaValidationError


def sync_and_validate_pipeline_state(
    context: ExecutionContext,
    run_state: PipelineRunState,
    state_validator: RuntimeSchemaValidator,
) -> None:
    context.sync_pipeline_state_from_run_state(run_state)
    payload = context.pipeline_state.model_dump(mode="json")
    try:
        errors = state_validator.validate_pipeline_state(payload)
    except SchemaValidationError as exc:
        raise ValueError(f"Invalid pipeline_state payload: {exc}") from exc

    if errors:
        raise ValueError("Invalid pipeline_state payload: " + "; ".join(errors))


def build_checkpoint_payload(
    context: ExecutionContext,
    run_state: PipelineRunState,
    status: str,
) -> dict[str, Any]:
    retry_metadata: dict[str, dict[str, Any]] = {}
    for step in run_state.steps:
        retry_metadata[step.name] = {
            "attempts": step.attempts,
            "status": step.status.value,
            "input_hash": step.input_hash,
            "error": step.error,
        }

    step_results_snapshot = context.snapshot_step_results()
    context_snapshot = context.snapshot_state()

    # Cache run_state serialization to avoid double serialization
    run_state_dict = run_state.to_dict()

    return {
        "run_id": context.run_id,
        "pipeline_name": context.pipeline_name,
        "status": status,
        "steps": step_results_snapshot,
        "run_state": run_state_dict,
        "checkpoint": {
            "step_cursor": run_state.current_step_index,
            "run_status": run_state.run_status,
            "context_snapshot": context_snapshot,
            "step_results_snapshot": step_results_snapshot,
            "run_state_snapshot": run_state_dict,
            "retry_metadata": retry_metadata,
        },
    }


def emit_checkpoint(
    context: ExecutionContext,
    run_state: PipelineRunState,
    checkpoint_lock: RLock,
    state_validator: RuntimeSchemaValidator,
    status: str | None = None,
) -> None:
    sync_and_validate_pipeline_state(
        context=context, run_state=run_state, state_validator=state_validator
    )
    callback = context.metadata.get("__checkpoint_callback")
    if not callable(callback):
        return

    checkpoint_status = status or run_state.run_status or StepStatus.RUNNING.value
    payload = build_checkpoint_payload(
        context=context,
        run_state=run_state,
        status=checkpoint_status,
    )
    with checkpoint_lock:
        callback(payload)
