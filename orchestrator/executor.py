from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from agents.schemas import AgentOutput
from hordeforge_utils import resolve_path
from logging_utils import redact_mapping
from orchestrator.agent_runner import (
    AgentContext,
    create_registry_from_factory,
    run_agent,
)
from orchestrator.context import ExecutionContext
from orchestrator.input_mapping import apply_input_mapping as _apply_input_mapping_fn
from orchestrator.loader import StepDefinition
from orchestrator.output_coercion import (
    coerce_code_patch_content_for_validation,
    coerce_decisions_for_validation,
    coerce_spec_content_for_validation,
    coerce_test_results_for_validation,
    coerce_tests_content_for_validation,
    error_result,
    normalize_agent_output,
    normalize_step_status,
)
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator
from registry.agents import AgentRegistry
from registry.bootstrap import init_registries
from registry.runtime_adapter import RuntimeRegistryAdapter


class StepExecutor:
    def __init__(
        self,
        *,
        agent_registry: RuntimeRegistryAdapter | AgentRegistry | None = None,
        agent_factory: Callable[[str], Any] | None = None,
        schema_validator: RuntimeSchemaValidator | None = None,
        strict_schema_validation: bool = True,
        schema_dir: str = "contracts/schemas",
    ):
        if agent_registry is not None:
            if isinstance(agent_registry, RuntimeRegistryAdapter):
                self.agent_registry = agent_registry
            elif isinstance(agent_registry, AgentRegistry):
                self.agent_registry = RuntimeRegistryAdapter(agent_registry)
            else:
                self.agent_registry = agent_registry
        elif agent_factory is not None:
            base_registry = RuntimeRegistryAdapter(AgentRegistry())
            self.agent_registry = create_registry_from_factory(base_registry, agent_factory)
        else:
            registries = init_registries(contracts_dir=schema_dir)
            self.agent_registry = RuntimeRegistryAdapter(registries["agent_registry"])

        self.strict_schema_validation = strict_schema_validation
        self.schema_validator = schema_validator or RuntimeSchemaValidator(
            schema_dir=schema_dir,
            strict_mode=strict_schema_validation,
        )
        self.logger = logging.getLogger("hordeforge.orchestrator.step_executor")

    @staticmethod
    def _normalize_agent_output(output):
        return normalize_agent_output(output)

    @staticmethod
    def _coerce_decisions_for_validation(decisions):
        return coerce_decisions_for_validation(decisions)

    @staticmethod
    def _coerce_code_patch_content_for_validation(content):
        return coerce_code_patch_content_for_validation(content)

    @staticmethod
    def _coerce_spec_content_for_validation(content):
        return coerce_spec_content_for_validation(content)

    @staticmethod
    def _coerce_tests_content_for_validation(content):
        return coerce_tests_content_for_validation(content)

    @staticmethod
    def _coerce_test_results_for_validation(content):
        return coerce_test_results_for_validation(content)

    @staticmethod
    def _normalize_step_status(status):
        return normalize_step_status(status)

    @staticmethod
    def _error_result(error_message, exception=None):
        return error_result(error_message)

    @staticmethod
    def _resolve_path(source, dotted_path):
        return resolve_path(source, dotted_path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _stable_hash(payload: dict[str, Any]) -> str:
        normalized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(normalized.encode("utf-8")).hexdigest()

    def calculate_step_input_hash(self, step: StepDefinition, context_state: dict[str, Any]) -> str:
        payload = _apply_input_mapping_fn(step, context_state)
        if not isinstance(payload, dict):
            payload = {"_payload": payload}
        return self._stable_hash(payload)

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
    def _resolve_step_end_log_level(step_status: StepStatus) -> int:
        if step_status == StepStatus.SUCCESS:
            return logging.INFO
        if step_status == StepStatus.PARTIAL_SUCCESS:
            return logging.WARNING
        if step_status == StepStatus.SKIPPED:
            return logging.INFO
        return logging.ERROR

    @staticmethod
    def _extract_primary_reason(output: dict[str, Any]) -> str | None:
        decisions = output.get("decisions")
        if isinstance(decisions, list):
            for item in decisions:
                if not isinstance(item, dict):
                    continue
                reason = item.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return reason.strip()
        logs = output.get("logs")
        if isinstance(logs, list):
            for item in logs:
                if isinstance(item, str) and item.strip():
                    return item.strip()[:300]
        return None

    def _get_agent_from_registry(self, agent_name: str, run_id: str) -> Any:
        if not self.agent_registry.has(agent_name):
            error_msg = f"Agent '{agent_name}' is not registered in AgentRegistry"
            self._log_event(
                logging.ERROR,
                run_id,
                "agent_not_found_in_registry",
                agent=agent_name,
                error=error_msg,
            )
            raise LookupError(error_msg)

        return self.agent_registry.create(agent_name)

    def _sanitize_output_for_validation(self, output: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "schema_version",
            "status",
            "artifacts",
            "decisions",
            "logs",
            "next_actions",
            "validation_errors",
            "test_results",
        }
        sanitized = {key: value for key, value in output.items() if key in allowed_keys}

        raw_status = sanitized.get("status")
        if isinstance(raw_status, str):
            status_upper = raw_status.strip().upper()
            if status_upper in {"FAILURE", "ERROR", "FAIL"}:
                status_upper = "FAILED"
            if status_upper:
                sanitized["status"] = status_upper

        if "decisions" not in sanitized:
            reason = output.get("reason")
            if isinstance(reason, str) and reason.strip():
                confidence = output.get("confidence")
                if not isinstance(confidence, (int, float)):
                    confidence = 0.5
                confidence = max(0.0, min(float(confidence), 1.0))
                sanitized["decisions"] = [{"reason": reason.strip(), "confidence": confidence}]

        if "decisions" in sanitized:
            sanitized["decisions"] = coerce_decisions_for_validation(sanitized.get("decisions"))

        if "test_results" in sanitized:
            sanitized["test_results"] = coerce_test_results_for_validation(
                sanitized.get("test_results")
            )

        artifacts = sanitized.get("artifacts")
        if isinstance(artifacts, list):
            normalized_artifacts = []
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    normalized_artifacts.append(artifact)
                    continue

                normalized_artifact = {
                    key: artifact[key]
                    for key in ("type", "path", "content", "metadata")
                    if key in artifact
                }
                artifact_type = artifact.get("type")
                if artifact_type == "code_patch":
                    normalized_artifact["content"] = coerce_code_patch_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "spec":
                    normalized_artifact["content"] = coerce_spec_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "tests":
                    normalized_artifact["content"] = coerce_tests_content_for_validation(
                        artifact.get("content")
                    )

                normalized_artifacts.append(normalized_artifact)
            sanitized["artifacts"] = normalized_artifacts

        return sanitized

    @staticmethod
    def _extract_output_aliases(output_mapping: Any) -> set[str]:
        aliases: set[str] = set()

        if isinstance(output_mapping, str):
            stripped = output_mapping.strip()
            if stripped and "{{" not in stripped and "}}" not in stripped:
                aliases.add(stripped)
            for match in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", output_mapping):
                if match:
                    aliases.add(match)
            return aliases

        if isinstance(output_mapping, dict):
            for value in output_mapping.values():
                aliases.update(StepExecutor._extract_output_aliases(value))
            return aliases

        if isinstance(output_mapping, list):
            for value in output_mapping:
                aliases.update(StepExecutor._extract_output_aliases(value))

        return aliases

    @staticmethod
    def _extract_output_payload(output: dict[str, Any]) -> Any:
        artifacts = output.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if isinstance(artifact, dict) and "content" in artifact:
                    return artifact.get("content")

        if "test_results" in output:
            return output.get("test_results")

        return output

    def _apply_output_mapping(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        output: dict[str, Any],
    ) -> None:
        aliases = self._extract_output_aliases(step.output_mapping)
        if not aliases:
            return

        mapped_value = self._extract_output_payload(output)

        for alias in aliases:
            if not alias:
                continue
            parts = alias.split(".")
            if len(parts) == 1:
                context.set_state_value(alias, mapped_value)
                continue

            root = parts[0]
            nested = context.state.get(root)
            if not isinstance(nested, dict):
                nested = {}

            cursor = nested
            for part in parts[1:-1]:
                value = cursor.get(part)
                if not isinstance(value, dict):
                    value = {}
                    cursor[part] = value
                cursor = value

            cursor[parts[-1]] = mapped_value
            context.set_state_value(root, nested)

    @staticmethod
    def _attach_artifact_ids(
        output: dict[str, Any],
        *,
        step_name: str,
        step_input_hash: str,
    ) -> list[str]:
        artifact_ids: list[str] = []
        artifacts = output.get("artifacts")
        if not isinstance(artifacts, list):
            return artifact_ids

        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            artifact_type = str(artifact.get("type") or "unknown").strip() or "unknown"
            digest_seed = f"{step_name}:{step_input_hash}:{artifact_type}:{index}"
            artifact_id = sha256(digest_seed.encode("utf-8")).hexdigest()[:20]
            metadata = artifact.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.setdefault("artifact_id", artifact_id)
            metadata.setdefault("step_input_hash", step_input_hash)
            artifact["metadata"] = metadata
            artifact_ids.append(str(metadata["artifact_id"]))

        return artifact_ids

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
        step_payload_for_hash = _apply_input_mapping_fn(step, context.state)
        if not isinstance(step_payload_for_hash, dict):
            step_payload_for_hash = {"_payload": step_payload_for_hash}
        step_input_hash = self._stable_hash(step_payload_for_hash)
        run_state.mark_step_status(
            step.name,
            StepStatus.RUNNING,
            started_at=started_at,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
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
            input_hash=step_input_hash,
        )

        error_message: str | None = None
        try:
            agent = self._get_agent_from_registry(step.agent, run_id)

            step_payload = dict(step_payload_for_hash)

            self._log_event(
                logging.DEBUG,
                run_id,
                "about_to_run_agent",
                step_name=step.name,
                agent=step.agent,
                payload_keys=list(step_payload.keys())
                if isinstance(step_payload, dict)
                else type(step_payload).__name__,
            )

            mapped_overrides: dict[str, Any] = {}
            if step.input_mapping and isinstance(step_payload, dict):
                mapped_overrides = {
                    key: step_payload[key] for key in step.input_mapping if key in step_payload
                }

            agent_context = AgentContext(context, mapped_overrides)

            output = run_agent(agent, agent_context, step.timeout_seconds)
            if not isinstance(output, dict):
                raise TypeError("Agent output must be a dict")

            try:
                AgentOutput.model_validate(output)
            except Exception as validation_exc:
                self._log_event(
                    logging.WARNING,
                    run_id,
                    "agent_output_pydantic_validation_warning",
                    step_name=step.name,
                    agent=step.agent,
                    validation_error=str(validation_exc),
                )

            self._log_event(
                logging.DEBUG,
                run_id,
                "agent_execution_completed",
                step_name=step.name,
                agent=step.agent,
                output_status=output.get("status", "unknown"),
            )

            validation_payload = self._sanitize_output_for_validation(output)

            validation_errors = self.schema_validator.validate_step_output(
                step.name, validation_payload
            )
            if validation_errors:
                normalized_output = normalize_agent_output(validation_payload)
                existing_errors = normalized_output.get("validation_errors", [])
                normalized_errors = (
                    list(existing_errors) if isinstance(existing_errors, list) else []
                )
                normalized_errors.extend(validation_errors)
                normalized_output["validation_errors"] = normalized_errors
                output = normalized_output
                if self.strict_schema_validation:
                    error_message = "; ".join(validation_errors)
                    self._log_event(
                        logging.WARNING,
                        run_id,
                        "step_validation_error",
                        step_name=step.name,
                        agent=step.agent,
                        validation_error_count=len(validation_errors),
                        strict_mode=self.strict_schema_validation,
                    )
                    output = error_result(f"Schema validation failed: {error_message}")
                else:
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
            else:
                output = normalize_agent_output(validation_payload)

            step_status = normalize_step_status(output.get("status"))
        except Exception as exc:  # pylint: disable=broad-except
            error_message = str(exc)
            self._log_event(
                logging.ERROR,
                run_id,
                "agent_execution_failed",
                step_name=step.name,
                agent=step.agent,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            output = error_result(f"Agent '{step.agent}' failed: {exc}")
            step_status = StepStatus.FAILED

        if step_status in {StepStatus.SUCCESS, StepStatus.PARTIAL_SUCCESS, StepStatus.BLOCKED}:
            try:
                self._apply_output_mapping(step, context, output)
            except Exception as exc:  # pylint: disable=broad-except
                self._log_event(
                    logging.WARNING,
                    run_id,
                    "output_mapping_failed",
                    step_name=step.name,
                    agent=step.agent,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        _ = self._attach_artifact_ids(output, step_name=step.name, step_input_hash=step_input_hash)
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
            input_hash=step_input_hash,
        )
        self._log_event(
            self._resolve_step_end_log_level(step_status),
            run_id,
            "step_end",
            step_name=step.name,
            agent=step.agent,
            pipeline_name=context.pipeline_name,
            status=step_status.value,
            reason=self._extract_primary_reason(output),
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
        )
        return output
