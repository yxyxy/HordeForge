from __future__ import annotations

from datetime import datetime
from typing import Any

from orchestrator.state import PipelineRunState


class RunSummaryBuilder:
    @staticmethod
    def _duration_seconds(started_at: str | None, finished_at: str | None) -> float:
        if not started_at or not finished_at:
            return 0.0
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        return max(0.0, (finished - started).total_seconds())

    def build(
        self, run_state: PipelineRunState, step_results: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        errors: list[dict[str, str]] = []
        total_retries = 0
        step_durations_seconds: dict[str, float] = {}
        step_retries: dict[str, int] = {}

        for step in run_state.steps:
            status_counts[step.status.value] = status_counts.get(step.status.value, 0) + 1
            if step.error:
                errors.append({"step": step.name, "error": step.error})
            if step.attempts > 1:
                total_retries += step.attempts - 1
            step_retries[step.name] = max(0, step.attempts - 1)
            step_durations_seconds[step.name] = self._duration_seconds(
                step.started_at, step.finished_at
            )

        return {
            "run_id": run_state.run_id,
            "pipeline_name": run_state.pipeline_name,
            "correlation_id": run_state.correlation_id,
            "trace_id": run_state.trace_id,
            "run_status": run_state.run_status,
            "step_count": len(run_state.steps),
            "status_counts": status_counts,
            "total_retries": total_retries,
            "errors": errors,
            "step_results_count": len(step_results),
            "step_retries": step_retries,
            "step_durations_seconds": step_durations_seconds,
        }
