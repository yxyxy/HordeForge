from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from importlib import import_module
from typing import Any
from uuid import uuid4

from agents.registry import AGENT_REGISTRY, AgentRegistry
from logging_utils import redact_mapping
from orchestrator.context import ExecutionContext
from orchestrator.loader import StepDefinition
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator


class StepExecutor:
    def __init__(
        self,
        agent_factory: Callable[[str], Any] | None = None,
        *,
        agent_registry: AgentRegistry | None = None,
        enable_dynamic_fallback: bool = True,
        fallback_allowlist: set[str] | None = None,
        schema_validator: RuntimeSchemaValidator | None = None,
        strict_schema_validation: bool = True,
        schema_dir: str = "contracts/schemas",
    ):
        self.agent_factory = agent_factory
        self._uses_custom_factory = agent_factory is not None
        self.agent_registry = agent_registry or AGENT_REGISTRY
        self.enable_dynamic_fallback = enable_dynamic_fallback
        self.fallback_allowlist = (
            set(fallback_allowlist) if fallback_allowlist is not None else None
        )
        self.strict_schema_validation = strict_schema_validation
        self.schema_validator = schema_validator or RuntimeSchemaValidator(
            schema_dir=schema_dir,
            strict_mode=strict_schema_validation,
        )
        self.logger = logging.getLogger("hordeforge.orchestrator.step_executor")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_event(self, level: int, run_id: str, event: str, **fields: Any) -> None:
        safe_fields = redact_mapping(fields)
        correlation_id = safe_fields.pop("correlation_id", None)
        step = safe_fields.pop("step", safe_fields.pop("step_name", None))
        payload = {
            "timestamp": self._now_iso(),
            "level": logging.getLevelName(level),
            "component": "step_executor",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "step": step,
            "event": event,
            **safe_fields,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _dynamic_import_agent(agent_name: str) -> Any:
        module = import_module(f"agents.{agent_name}")
        class_name = "".join(part.capitalize() for part in agent_name.split("_"))
        if not hasattr(module, class_name):
            raise AttributeError(f"Class '{class_name}' not found in module agents.{agent_name}")
        agent_class = getattr(module, class_name)
        return agent_class()

    def _fallback_allowed(self, agent_name: str) -> bool:
        if not self.enable_dynamic_fallback:
            return False
        if self.fallback_allowlist is None:
            return True
        return agent_name in self.fallback_allowlist

    def _default_agent_factory(self, agent_name: str, run_id: str) -> Any:
        if self.agent_registry.has(agent_name):
            return self.agent_registry.create(agent_name)

        if not self._fallback_allowed(agent_name):
            raise LookupError(
                f"Agent '{agent_name}' not found in registry and dynamic fallback is disabled"
            )

        self._log_event(
            logging.WARNING,
            run_id,
            "agent_registry_fallback",
            agent=agent_name,
            reason="missing_registry_entry",
        )
        agent = self._dynamic_import_agent(agent_name)
        if not self.agent_registry.has(agent_name):
            self.agent_registry.register(agent_name, agent.__class__)
        return agent

    @staticmethod
    def _normalize_step_status(raw_status: str | None) -> StepStatus:
        if raw_status in {StepStatus.SUCCESS.value, "PARTIAL_SUCCESS"}:
            return StepStatus.SUCCESS
        if raw_status in {item.value for item in StepStatus}:
            return StepStatus(raw_status)
        return StepStatus.FAILED

    @staticmethod
    def _error_result(message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "artifacts": [],
            "decisions": [],
            "logs": [message],
            "next_actions": [],
        }

    @staticmethod
    def _run_agent(
        agent: Any, payload: dict[str, Any], timeout_seconds: float | None
    ) -> dict[str, Any]:
        if timeout_seconds is None:
            return agent.run(payload)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(agent.run, payload)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeoutError as exc:
                raise TimeoutError(f"Step timed out after {timeout_seconds} seconds") from exc

    def execute_step(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        run_state: PipelineRunState,
    ) -> dict[str, Any]:
        run_id = context.run_id
        correlation_id = str(context.metadata.get("correlation_id", "")).strip() or None
        trace_id = str(context.metadata.get("trace_id", "")).strip() or None
        parent_span_id = str(context.metadata.get("root_span_id", "")).strip() or None
        span_id = uuid4().hex[:16]
        started_at = self._now_iso()
        run_state.mark_step_status(
            step.name,
            StepStatus.RUNNING,
            started_at=started_at,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        self._log_event(
            logging.INFO,
            run_id,
            "step_start",
            step_name=step.name,
            agent=step.agent,
            pipeline_name=context.pipeline_name,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )

        error_message: str | None = None
        try:
            if self._uses_custom_factory and self.agent_factory is not None:
                agent = self.agent_factory(step.agent)
            else:
                agent = self._default_agent_factory(step.agent, run_id)
            output = self._run_agent(agent, context.state, step.timeout_seconds)
            if not isinstance(output, dict):
                raise TypeError("Agent output must be a dict")
            validation_errors = self.schema_validator.validate_step_output(step.name, output)
            if validation_errors:
                existing_errors = output.get("validation_errors")
                normalized_errors = (
                    list(existing_errors) if isinstance(existing_errors, list) else []
                )
                normalized_errors.extend(validation_errors)
                output["validation_errors"] = normalized_errors
                error_message = "; ".join(validation_errors)
                self._log_event(
                    logging.WARNING,
                    run_id,
                    "step_validation_warning",
                    step_name=step.name,
                    agent=step.agent,
                    validation_error_count=len(validation_errors),
                    strict_mode=self.strict_schema_validation,
                )
            step_status = self._normalize_step_status(output.get("status"))
        except Exception as exc:  # pylint: disable=broad-except
            error_message = str(exc)
            output = self._error_result(f"Agent '{step.agent}' failed: {exc}")
            step_status = StepStatus.FAILED

        context.record_step_result(step.name, output)
        finished_at = self._now_iso()
        run_state.mark_step_status(
            step.name,
            step_status,
            finished_at=finished_at,
            error=error_message,
            output=output,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        self._log_event(
            logging.INFO if step_status == StepStatus.SUCCESS else logging.ERROR,
            run_id,
            "step_end",
            step_name=step.name,
            agent=step.agent,
            pipeline_name=context.pipeline_name,
            status=step_status.value,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        return output
