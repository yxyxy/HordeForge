from __future__ import annotations

from datetime import datetime
from typing import Any

from orchestrator.state import PipelineRunState


class RunSummaryBuilder:
    @staticmethod
    def _extract_artifact_content(
        step_output: dict[str, Any],
        artifact_type: str,
    ) -> dict[str, Any] | None:
        artifacts = step_output.get("artifacts")
        if not isinstance(artifacts, list):
            return None
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("type") != artifact_type:
                continue
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
        return None

    @staticmethod
    def _is_pr_reached(pr_merge_status: str | None) -> bool:
        return pr_merge_status in {"SUCCESS", "PARTIAL_SUCCESS"}

    def _resolve_pr_summary(
        self,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> tuple[bool, str | None, bool]:
        step_names = {step.name for step in run_state.steps}
        if "pr_merge_agent" not in step_names:
            return False, None, False

        merge_output = step_results.get("pr_merge_agent")
        if not isinstance(merge_output, dict):
            return False, "NOT_EXECUTED", False

        pr_merge_status = str(merge_output.get("status") or "").strip().upper() or "UNKNOWN"
        merged = False
        merge_payload = self._extract_artifact_content(merge_output, "merge_status")
        if isinstance(merge_payload, dict):
            merged = bool(merge_payload.get("merged") is True)

        return self._is_pr_reached(pr_merge_status), pr_merge_status, merged

    @staticmethod
    def _collect_blocked_step_names(step_results: dict[str, dict[str, Any]]) -> list[str]:
        blocked_steps = [
            step_name
            for step_name, output in step_results.items()
            if isinstance(output, dict) and str(output.get("status", "")).upper() == "BLOCKED"
        ]
        blocked_steps.sort()
        return blocked_steps

    def _is_env_missing_secret_block(self, step_output: dict[str, Any]) -> bool:
        decisions = step_output.get("decisions")
        if isinstance(decisions, list):
            for decision in decisions:
                if not isinstance(decision, dict):
                    continue
                reason = str(decision.get("reason", "")).strip().lower()
                if "env_doctor_missing_required_secrets" in reason:
                    return True
                if "missing required secret" in reason:
                    return True

        logs = step_output.get("logs")
        if isinstance(logs, list):
            for entry in logs:
                text = str(entry).strip().lower()
                if "missing_required_secrets" in text:
                    return True
                if "missing required secret" in text:
                    return True
                if "env_doctor_blocked=true" in text:
                    return True

        for artifact_type in ("test_results", "env_doctor_report"):
            payload = self._extract_artifact_content(step_output, artifact_type)
            if not isinstance(payload, dict):
                continue
            stderr = str(payload.get("stderr", "")).strip().lower()
            if "missing required secret" in stderr:
                return True
            env_doctor = payload.get("env_doctor")
            if isinstance(env_doctor, dict):
                missing = env_doctor.get("missing_required_secrets")
                if isinstance(missing, list) and len(missing) > 0:
                    return True

        test_results = step_output.get("test_results")
        if isinstance(test_results, dict):
            stderr = str(test_results.get("stderr", "")).strip().lower()
            if "missing required secret" in stderr:
                return True
            env_doctor = test_results.get("env_doctor")
            if isinstance(env_doctor, dict):
                missing = env_doctor.get("missing_required_secrets")
                if isinstance(missing, list) and len(missing) > 0:
                    return True

        return False

    def _resolve_blocked_by(
        self,
        blocked_steps: list[str],
        step_results: dict[str, dict[str, Any]],
    ) -> str | None:
        if not blocked_steps:
            return None
        for step_name in blocked_steps:
            step_output = step_results.get(step_name)
            if isinstance(step_output, dict) and self._is_env_missing_secret_block(step_output):
                return "env_missing_secrets"
        return "step_blocked"

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

        pr_reached, pr_merge_status, pr_merged = self._resolve_pr_summary(run_state, step_results)
        blocked_steps = self._collect_blocked_step_names(step_results)
        blocked_by = self._resolve_blocked_by(blocked_steps, step_results)

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
            "pr_reached": pr_reached,
            "pr_merge_status": pr_merge_status,
            "pr_merged": pr_merged,
            "blocked_steps": blocked_steps,
            "blocked_by": blocked_by,
        }
