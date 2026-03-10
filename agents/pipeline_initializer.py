from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_step_status


class PipelineInitializer:
    name = "pipeline_initializer"
    description = "Aggregates init step results into final pipeline_status."

    REQUIRED_STEPS = ("repo_connector", "rag_initializer", "memory_agent")
    OPTIONAL_STEPS = ("architecture_evaluator", "test_analyzer")

    def run(self, context: dict[str, Any]) -> dict:
        tracked_steps = list(self.REQUIRED_STEPS) + list(self.OPTIONAL_STEPS)
        step_statuses = {
            step_name: get_step_status(context, step_name) for step_name in tracked_steps
        }

        hard_failure = any(
            step_statuses.get(step_name) in {"FAILED", "BLOCKED", "MISSING"}
            for step_name in self.REQUIRED_STEPS
        )
        init_ready = not hard_failure
        status = "SUCCESS" if init_ready else "PARTIAL_SUCCESS"

        pipeline_status = {
            "pipeline": "init_pipeline",
            "init_ready": init_ready,
            "steps": step_statuses,
            "summary": {
                "success_count": sum(1 for item in step_statuses.values() if item == "SUCCESS"),
                "partial_count": sum(
                    1 for item in step_statuses.values() if item == "PARTIAL_SUCCESS"
                ),
                "failure_count": sum(
                    1 for item in step_statuses.values() if item in {"FAILED", "BLOCKED", "MISSING"}
                ),
            },
        }
        return build_agent_result(
            status=status,
            artifact_type="pipeline_status",
            artifact_content=pipeline_status,
            reason="Init pipeline summary generated from upstream step statuses.",
            confidence=0.9 if init_ready else 0.72,
            logs=["Pipeline initializer aggregated init flow statuses."],
            next_actions=["feature_pipeline"] if init_ready else ["request_human_review"],
        )
