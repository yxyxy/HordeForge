import json
import logging
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from logging_utils import redact_mapping
from orchestrator.loader import PipelineLoader

logger = logging.getLogger("hordeforge.runner")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(level: int, run_id: str, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    correlation_id = safe_fields.pop("correlation_id", None)
    step = safe_fields.pop("step", safe_fields.pop("step_name", None))
    payload = {
        "timestamp": _utc_now_iso(),
        "level": logging.getLevelName(level),
        "component": "pipeline_runner",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "step": step,
        "event": event,
        **safe_fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False))


class PipelineRunner:
    """Minimal orchestration runner for pipeline development."""

    def __init__(self, pipelines_dir: str = "pipelines"):
        self.pipeline_loader = PipelineLoader(pipelines_dir=pipelines_dir)

    def run(
        self,
        pipeline_name: str,
        inputs: dict[str, Any] | None = None,
        run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        pipeline = self._load_pipeline(pipeline_name)
        steps = pipeline.get("steps", [])
        context: dict[str, Any] = dict(inputs or {})
        step_results: dict[str, Any] = {}
        final_status = "SUCCESS"
        run_ref = run_id or "n/a"

        _log_event(
            logging.INFO,
            run_ref,
            "pipeline_start",
            pipeline_name=pipeline_name,
            step_count=len(steps),
            correlation_id=correlation_id,
        )

        for index, step in enumerate(steps, start=1):
            step_name = step.get("name", f"step_{index}")
            agent_name = step.get("agent")
            on_failure = step.get("on_failure", "stop_pipeline")

            _log_event(
                logging.INFO,
                run_ref,
                "step_start",
                pipeline_name=pipeline_name,
                step_name=step_name,
                agent=agent_name,
                step_index=index,
                correlation_id=correlation_id,
            )

            if not agent_name:
                result = self._error_result(
                    "FAILED",
                    f"Step '{step_name}' has no agent configured",
                )
                step_results[step_name] = result
                final_status = "FAILED"
                _log_event(
                    logging.ERROR,
                    run_ref,
                    "step_end",
                    pipeline_name=pipeline_name,
                    step_name=step_name,
                    status="FAILED",
                    reason="missing_agent",
                    correlation_id=correlation_id,
                )
                break

            try:
                agent_class = self._import_agent(agent_name)
                agent = agent_class()
                output = agent.run(context)
                if not isinstance(output, dict):
                    raise TypeError("Agent output must be a dict")
            except Exception as exc:  # pylint: disable=broad-except
                output = self._error_result(
                    "FAILED",
                    f"Agent '{agent_name}' failed: {exc}",
                )

            status = output.get("status", "FAILED")
            step_results[step_name] = output
            context[step_name] = output
            _log_event(
                logging.INFO if status not in {"FAILED", "BLOCKED"} else logging.ERROR,
                run_ref,
                "step_end",
                pipeline_name=pipeline_name,
                step_name=step_name,
                status=status,
                correlation_id=correlation_id,
            )

            if status in {"FAILED", "BLOCKED"}:
                final_status = status
                if on_failure in {
                    "stop_pipeline",
                    "escalate_to_human",
                    "create_issue_for_human",
                }:
                    break
            elif status == "PARTIAL_SUCCESS" and final_status == "SUCCESS":
                final_status = "PARTIAL_SUCCESS"

        _log_event(
            logging.INFO if final_status not in {"FAILED", "BLOCKED"} else logging.ERROR,
            run_ref,
            "pipeline_end",
            pipeline_name=pipeline_name,
            status=final_status,
            correlation_id=correlation_id,
        )

        return {
            "status": final_status,
            "pipeline_name": pipeline.get("pipeline_name", pipeline_name),
            "steps": step_results,
        }

    def _load_pipeline(self, pipeline_name: str) -> dict[str, Any]:
        return self.pipeline_loader.load(pipeline_name).to_dict()

    def _import_agent(self, agent_name: str):
        module = import_module(f"agents.{agent_name}")
        class_name = "".join(part.capitalize() for part in agent_name.split("_"))
        if not hasattr(module, class_name):
            raise AttributeError(f"Class '{class_name}' not found in module agents.{agent_name}")
        return getattr(module, class_name)

    @staticmethod
    def _error_result(status: str, message: str) -> dict[str, Any]:
        return {
            "status": status,
            "artifacts": [],
            "decisions": [],
            "logs": [message],
            "next_actions": [],
        }
