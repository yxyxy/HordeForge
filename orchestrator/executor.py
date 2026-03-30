from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from logging_utils import redact_mapping
from orchestrator.context import ExecutionContext
from orchestrator.loader import StepDefinition
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator
from registry.agents import AgentMetadata, AgentRegistry
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
            self.agent_registry = self._create_registry_from_factory(base_registry, agent_factory)
        else:
            registries = init_registries(contracts_dir=schema_dir)
            self.agent_registry = RuntimeRegistryAdapter(registries["agent_registry"])

        self.strict_schema_validation = strict_schema_validation
        self.schema_validator = schema_validator or RuntimeSchemaValidator(
            schema_dir=schema_dir,
            strict_mode=strict_schema_validation,
        )
        self.logger = logging.getLogger("hordeforge.orchestrator.step_executor")

    def _create_registry_from_factory(self, base_registry, factory):
        """Создает обертку реестра, который использует фабрику для создания агентов."""

        # Создаем обертку вокруг базового реестра, которая может динамически регистрировать агентов
        class DynamicRegistryWrapper:
            def __init__(self, base_reg, factory_func):
                self.base_registry = base_reg
                self.factory = factory_func
                self.dynamic_agents = {}

            def has(self, agent_name: str) -> bool:
                # Проверяем сначала в базовом реестре, затем пробуем фабрику
                if self.base_registry.has(agent_name):
                    return True

                # Пробуем создать агент через фабрику, чтобы проверить его наличие
                try:
                    agent = self.factory(agent_name)
                    # Сохраняем агент во временный кэш
                    self.dynamic_agents[agent_name] = agent.__class__
                    return True
                except Exception:
                    return False

            def create(self, agent_name: str) -> Any:
                # Если агент в базовом реестре - используем его
                if self.base_registry.has(agent_name):
                    return self.base_registry.create(agent_name)

                # Иначе создаем через фабрику каждый раз, чтобы избежать проблем с состоянием
                agent = self.factory(agent_name)
                return agent

            def get(self, agent_name: str):
                # Для совместимости с интерфейсом AgentRegistry
                if self.base_registry.has(agent_name):
                    item = self.base_registry.get(agent_name)
                    if isinstance(item, AgentMetadata):
                        return item.agent_class
                    return item

                if agent_name in self.dynamic_agents:
                    # Возвращаем класс агента, а не экземпляр
                    return self.dynamic_agents[agent_name]

                # Если агент не существует, пробуем создать через фабрику
                try:
                    agent = self.factory(agent_name)
                    self.dynamic_agents[agent_name] = agent.__class__
                    return agent.__class__
                except Exception:
                    # Если агент не существует, вызываем исключение как в оригинальном методе
                    raise KeyError(f"Agent '{agent_name}' is not registered") from None

        return DynamicRegistryWrapper(base_registry, factory)

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

    def _get_agent_from_registry(self, agent_name: str, run_id: str) -> Any:
        """Получить агент из реестра, с обработкой ошибок для незарегистрированных агентов."""
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

    @staticmethod
    def _normalize_agent_output(output: dict[str, Any]) -> dict[str, Any]:
        """
        Нормализует результат агента, чтобы он соответствовал схеме.
        Удаляет дополнительные поля, которые не предусмотрены схемой.
        """
        # Определяем допустимые поля в соответствии со схемой
        allowed_keys = {
            "status",
            "artifacts",
            "decisions",
            "logs",
            "next_actions",
            "validation_errors",
            "test_results",
            "schema_version",
        }

        # Создаем новый словарь только с разрешенными ключами
        normalized = {}
        for key in allowed_keys:
            if key in output:
                normalized[key] = output[key]

        # Если обязательные поля отсутствуют, добавляем их со значениями по умолчанию
        if "status" not in normalized:
            normalized["status"] = output.get("status", "FAILED")

        if "artifacts" not in normalized:
            normalized["artifacts"] = output.get("artifacts", [])

        if "decisions" not in normalized:
            normalized["decisions"] = output.get("decisions", [])

        if "logs" not in normalized:
            normalized["logs"] = output.get("logs", ["Normalized by StepExecutor"])

        if "next_actions" not in normalized:
            normalized["next_actions"] = output.get("next_actions", [])

        return normalized

    @staticmethod
    def _coerce_decisions_for_validation(decisions: Any) -> Any:
        if not isinstance(decisions, list):
            return decisions

        normalized_decisions: list[dict[str, Any]] = []
        for item in decisions:
            if isinstance(item, dict):
                reason = item.get("reason")
                confidence = item.get("confidence")
                if not isinstance(reason, str) or not reason.strip():
                    reason = str(reason) if reason is not None else str(item)
                if not isinstance(confidence, (int, float)):
                    confidence = 0.5
                confidence = max(0.0, min(float(confidence), 1.0))
                normalized_decisions.append({"reason": reason, "confidence": confidence})
                continue

            if isinstance(item, str):
                normalized_decisions.append({"reason": item, "confidence": 0.5})
                continue

            normalized_decisions.append({"reason": str(item), "confidence": 0.5})

        return normalized_decisions

    @staticmethod
    def _coerce_code_patch_content_for_validation(content: Any) -> dict[str, Any]:
        content_dict = content if isinstance(content, dict) else {}

        raw_files = content_dict.get("files")
        normalized_files: list[dict[str, str]] = []
        if isinstance(raw_files, list):
            for item in raw_files:
                if not isinstance(item, dict):
                    normalized_files.append({"path": "unknown_path", "diff": "# modify"})
                    continue

                path_value = item.get("path")
                path = str(path_value).strip() if path_value else "unknown_path"
                diff = item.get("diff")

                if isinstance(diff, str) and diff.strip():
                    normalized_files.append({"path": path, "diff": diff})
                    continue

                content_value = item.get("content")
                change_type = str(item.get("change_type") or "modify").strip() or "modify"
                if isinstance(content_value, str) and content_value.strip():
                    generated_diff = f"# {change_type}\n{content_value}"
                elif content_value is None:
                    generated_diff = f"# {change_type}"
                else:
                    generated_diff = (
                        f"# {change_type}\n{json.dumps(content_value, ensure_ascii=False)}"
                    )

                normalized_files.append({"path": path, "diff": generated_diff or "# modify"})

        if not normalized_files:
            normalized_files = [{"path": "unknown_path", "diff": "# modify"}]

        normalized_content: dict[str, Any] = {
            "schema_version": "1.0",
            "files": normalized_files,
        }

        decisions = content_dict.get("decisions")
        if isinstance(decisions, list):
            normalized_content["decisions"] = [str(item) for item in decisions]

        dry_run = content_dict.get("dry_run")
        if isinstance(dry_run, bool):
            normalized_content["dry_run"] = dry_run

        for key in ("expected_failures", "fix_iteration", "remaining_failures"):
            value = content_dict.get(key)
            if isinstance(value, int):
                normalized_content[key] = value
            elif value is not None:
                try:
                    normalized_content[key] = int(value)
                except (TypeError, ValueError):
                    continue

        # Preserve GitHub patch workflow metadata so downstream agents (e.g. pr_merge_agent)
        # can consume PR details from code_patch artifacts.
        pr_number = content_dict.get("pr_number")
        if isinstance(pr_number, int):
            normalized_content["pr_number"] = pr_number

        for key in ("pr_url", "branch_name", "apply_error"):
            value = content_dict.get(key)
            if isinstance(value, str) and value.strip():
                normalized_content[key] = value

        for key in ("applied_to_github", "rollback_performed", "llm_enhanced"):
            value = content_dict.get(key)
            if isinstance(value, bool):
                normalized_content[key] = value

        notes = content_dict.get("notes")
        if isinstance(notes, list):
            normalized_content["notes"] = [str(item) for item in notes]

        return normalized_content

    @staticmethod
    def _coerce_spec_content_for_validation(content: Any) -> dict[str, Any]:
        if not isinstance(content, dict):
            summary = str(content).strip() if content is not None else ""
            if not summary:
                summary = "Generated specification"
            return {
                "schema_version": "1.0",
                "summary": summary,
                "requirements": ["Define implementation details"],
            }

        summary_candidates = [
            content.get("summary"),
            content.get("feature_description"),
            content.get("title"),
            content.get("user_story"),
        ]
        summary = next(
            (
                str(candidate).strip()
                for candidate in summary_candidates
                if isinstance(candidate, str) and candidate.strip()
            ),
            "Generated specification",
        )

        requirements: list[str] = []
        raw_requirements = content.get("requirements")
        if isinstance(raw_requirements, list):
            for item in raw_requirements:
                if isinstance(item, str) and item.strip():
                    requirements.append(item.strip())
                elif isinstance(item, dict):
                    for key in ("description", "title", "name"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            requirements.append(value.strip())
                            break

        if not requirements:
            acceptance_criteria = content.get("acceptance_criteria")
            if isinstance(acceptance_criteria, list):
                for item in acceptance_criteria:
                    if isinstance(item, str) and item.strip():
                        requirements.append(item.strip())

        if not requirements:
            technical_spec = content.get("technical_specification")
            if isinstance(technical_spec, dict):
                for key in ("components", "implementation_notes", "dependencies"):
                    values = technical_spec.get(key)
                    if isinstance(values, list):
                        for item in values:
                            if isinstance(item, str) and item.strip():
                                requirements.append(item.strip())

        if not requirements:
            requirements = ["Define implementation details"]

        notes: list[str] = []
        raw_notes = content.get("notes")
        if isinstance(raw_notes, list):
            for item in raw_notes:
                if isinstance(item, str) and item.strip():
                    notes.append(item.strip())

        normalized_content: dict[str, Any] = {
            "schema_version": "1.0",
            "summary": summary,
            "requirements": requirements,
        }
        if notes:
            normalized_content["notes"] = notes

        return normalized_content

    @staticmethod
    def _coerce_tests_content_for_validation(content: Any) -> dict[str, Any]:
        content_dict = content if isinstance(content, dict) else {}

        normalized_cases: list[dict[str, str]] = []
        raw_cases = content_dict.get("test_cases")
        if isinstance(raw_cases, list):
            for index, case in enumerate(raw_cases, start=1):
                if isinstance(case, dict):
                    name = str(case.get("name") or f"test_case_{index}").strip()
                    test_type = str(case.get("type") or "unit").strip()
                    expected_result = str(case.get("expected_result") or "pass").strip()
                else:
                    name = f"test_case_{index}"
                    test_type = "unit"
                    expected_result = "pass"

                normalized_cases.append(
                    {
                        "name": name or f"test_case_{index}",
                        "type": test_type or "unit",
                        "expected_result": expected_result or "pass",
                    }
                )

        if not normalized_cases:
            normalized_cases.append(
                {
                    "name": "test_feature_baseline",
                    "type": "unit",
                    "expected_result": "pass",
                }
            )

        schema_version = str(content_dict.get("schema_version", "1.0")).strip()
        if schema_version not in {"1.0", "2.0"}:
            schema_version = "1.0"

        normalized_content: dict[str, Any] = {
            "schema_version": schema_version,
            "test_cases": normalized_cases,
        }

        language = content_dict.get("language")
        if isinstance(language, str):
            normalized_content["language"] = language

        framework = content_dict.get("framework")
        if isinstance(framework, str) or framework is None:
            normalized_content["framework"] = framework

        test_template = content_dict.get("test_template")
        if isinstance(test_template, str) or test_template is None:
            normalized_content["test_template"] = test_template

        test_patterns = content_dict.get("test_patterns")
        if isinstance(test_patterns, dict):
            normalized_content["test_patterns"] = test_patterns

        return normalized_content

    @staticmethod
    def _coerce_test_results_for_validation(test_results: Any) -> Any:
        if not isinstance(test_results, dict):
            return test_results

        passed_raw = test_results.get("passed")
        failed_raw = test_results.get("failed")
        total_raw = test_results.get("total")

        try:
            passed = int(passed_raw) if passed_raw is not None else 0
        except (TypeError, ValueError):
            passed = 0

        try:
            failed = int(failed_raw) if failed_raw is not None else 0
        except (TypeError, ValueError):
            failed = 0

        if total_raw is None:
            total = max(0, passed + failed)
        else:
            try:
                total = int(total_raw)
            except (TypeError, ValueError):
                total = max(0, passed + failed)

        normalized = {
            "total": max(0, total),
            "passed": max(0, passed),
            "failed": max(0, failed),
        }

        mode = test_results.get("mode")
        if isinstance(mode, str) and mode.strip():
            normalized["mode"] = mode

        return normalized

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
                status_upper = StepStatus.FAILED.value
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
            sanitized["decisions"] = self._coerce_decisions_for_validation(
                sanitized.get("decisions")
            )

        if "test_results" in sanitized:
            sanitized["test_results"] = self._coerce_test_results_for_validation(
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
                    normalized_artifact["content"] = self._coerce_code_patch_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "spec":
                    normalized_artifact["content"] = self._coerce_spec_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "tests":
                    normalized_artifact["content"] = self._coerce_tests_content_for_validation(
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
    def _normalize_step_status(raw_status: str | None) -> StepStatus:
        # PARTIAL_SUCCESS should remain as PARTIAL_SUCCESS, not normalized to SUCCESS
        if raw_status == StepStatus.PARTIAL_SUCCESS.value:
            return StepStatus.PARTIAL_SUCCESS
        if raw_status == StepStatus.SUCCESS.value:
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
    def _invoke_agent_run(agent: Any, payload: Any) -> Any:
        import inspect

        run_callable = agent.run
        bound_signature = inspect.signature(run_callable)
        positional_params = [
            parameter
            for parameter in bound_signature.parameters.values()
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]

        # Compatibility mode:
        # Some tests/agents define `def run(context)` on a class (without `self`),
        # which becomes a bound method with zero positional params.
        if not positional_params:
            raw_function = getattr(run_callable, "__func__", None)
            if raw_function is not None:
                raw_signature = inspect.signature(raw_function)
                raw_positional = [
                    parameter
                    for parameter in raw_signature.parameters.values()
                    if parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if len(raw_positional) == 1 and raw_positional[0].name not in {"self", "cls"}:
                    return raw_function(payload)
            return run_callable()

        return run_callable(payload)

    @staticmethod
    def _run_agent(agent: Any, payload: Any, timeout_seconds: float | None) -> dict[str, Any]:
        import asyncio
        import inspect

        def invoke_with_await_support() -> dict[str, Any]:
            result = StepExecutor._invoke_agent_run(agent, payload)
            if inspect.isawaitable(result):
                return asyncio.run(result)
            return result

        if timeout_seconds is None:
            return invoke_with_await_support()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(invoke_with_await_support)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeoutError as exc:
                raise TimeoutError(f"Step timed out after {timeout_seconds} seconds") from exc

    def _apply_input_mapping(
        self, step: StepDefinition, context_state: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Apply input_mapping from step definition to context state.

        Handles Jinja2 template variables like {{key}}, {{key.subkey}}, {{key|default(value)}}
        Resolves them from context_state and builds step-specific payload.

        Args:
            step: Step definition with input_mapping
            context_state: Current execution context state

        Returns:
            Merged payload for the agent
        """
        try:
            from jinja2 import Template
        except ImportError:
            # Fallback to simple regex-based resolution if Jinja2 not available
            return self._apply_input_mapping_simple(step, context_state)

        # Start with context state as base
        payload = dict(context_state)

        # If no input_mapping, return full context
        if not step.input_mapping:
            return payload

        scalar_template_pattern = re.compile(r"^\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}$")

        def resolve_value(raw_value: Any) -> Any:
            if not isinstance(raw_value, str):
                return raw_value

            match = scalar_template_pattern.fullmatch(raw_value.strip())
            if match:
                resolved_value = self._resolve_path(context_state, match.group(1))
                if resolved_value is not None:
                    return resolved_value

            try:
                template = Template(raw_value)
                rendered = template.render(**context_state)
                return self._try_parse_json(rendered)
            except Exception:
                return raw_value

        # Apply each mapping from input_mapping
        for target_key, source_value in step.input_mapping.items():
            if isinstance(source_value, str):
                payload[target_key] = resolve_value(source_value)
            elif isinstance(source_value, dict):
                resolved_dict = {k: resolve_value(v) for k, v in source_value.items()}
                payload[target_key] = resolved_dict
            elif isinstance(source_value, list):
                payload[target_key] = [resolve_value(item) for item in source_value]
            else:
                payload[target_key] = source_value

        return payload

    def _try_parse_json(self, value: str) -> Any:
        """Try to parse a string as JSON. Return original string if not valid JSON."""
        import json

        value = value.strip()
        if (value.startswith("{") and value.endswith("}")) or (
            value.startswith("[") and value.endswith("]")
        ):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass
        return value

    def _apply_input_mapping_simple(
        self, step: StepDefinition, context_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback simple input_mapping without Jinja2."""

        import re

        # Start with context state as base
        payload = dict(context_state)

        # If no input_mapping, return full context
        if not step.input_mapping:
            return payload

        # Pattern to match template variables: {{key}} or {{key.subkey}}
        template_pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}")

        def resolve_template(template_str: str) -> Any:
            """Resolve a template string like {{key.subkey}} from context_state."""
            # Find all template variables in the string
            matches = template_pattern.findall(template_str)

            if not matches:
                # No template variables, return as-is
                return template_str

            # If entire string is a single template variable, resolve it directly
            if len(matches) == 1 and template_str.strip() == f"{{{{{matches[0]}}}}}":
                return self._resolve_path(context_state, matches[0])

            # Otherwise, replace each template variable in the string
            result = template_str
            for match in matches:
                value = self._resolve_path(context_state, match)
                if value is not None:
                    # Replace the template with the resolved value
                    result = result.replace(f"{{{{{match}}}}}", str(value))
                else:
                    # Keep the template if not resolved
                    pass
            return result

        # Apply each mapping from input_mapping
        for target_key, source_value in step.input_mapping.items():
            if isinstance(source_value, str):
                # Try to resolve as template first
                resolved = resolve_template(source_value)
                payload[target_key] = resolved
            elif isinstance(source_value, dict):
                # For dict values, resolve each value
                resolved_dict = {}
                for k, v in source_value.items():
                    if isinstance(v, str):
                        resolved_dict[k] = resolve_template(v)
                    else:
                        resolved_dict[k] = v
                payload[target_key] = resolved_dict
            elif isinstance(source_value, list):
                # For list values, resolve each element
                resolved_list = []
                for item in source_value:
                    if isinstance(item, str):
                        resolved_list.append(resolve_template(item))
                    else:
                        resolved_list.append(item)
                payload[target_key] = resolved_list
            else:
                # For non-string values, use as-is
                payload[target_key] = source_value

        return payload

    @staticmethod
    def _resolve_path(source: dict[str, Any], dotted_path: str) -> Any:
        """Resolve a dotted path like 'key.subkey.array[0].field' from source dict."""
        current = source
        parts = dotted_path.split(".")

        for part in parts:
            if not isinstance(current, dict) or part not in current:
                # Try to handle array access like items[0]
                if "[" in part and "]" in part:
                    key, idx_str = part.split("[")
                    idx = int(idx_str.rstrip("]"))
                    if isinstance(current, dict) and key in current:
                        arr = current[key]
                        if isinstance(arr, list) and 0 <= idx < len(arr):
                            current = arr[idx]
                            continue
                return None
            current = current[part]

        return current

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
            # Всегда получаем агент через реестр, без возможности прямого создания
            agent = self._get_agent_from_registry(step.agent, run_id)

            # Apply input_mapping from step definition to context.state
            step_payload = self._apply_input_mapping(step, context.state)

            # Логируем информацию о вызове агента
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

            # Создаем контекст выполнения для агента, который включает в себя state и методы доступа к нему
            # Используем объект, который предоставляет доступ к состоянию как через атрибут state, так и через метод get

            mapped_overrides: dict[str, Any] = {}
            if step.input_mapping and isinstance(step_payload, dict):
                mapped_overrides = {
                    key: step_payload[key] for key in step.input_mapping if key in step_payload
                }

            class _StepStateView:
                def __init__(self, shared_state: dict[str, Any], overrides: dict[str, Any]):
                    self._shared_state = shared_state
                    self._overrides = dict(overrides)

                def get(self, key: str, default: Any = None) -> Any:
                    if key in self._overrides:
                        return self._overrides[key]
                    return self._shared_state.get(key, default)

                def __getitem__(self, key: str) -> Any:
                    if key in self._overrides:
                        return self._overrides[key]
                    return self._shared_state[key]

                def __setitem__(self, key: str, value: Any) -> None:
                    self._shared_state[key] = value
                    self._overrides[key] = value

                def __contains__(self, key: str) -> bool:
                    return key in self._overrides or key in self._shared_state

                def update(self, updates: dict[str, Any]) -> None:
                    self._shared_state.update(updates)
                    self._overrides.update(updates)

                def copy(self) -> dict[str, Any]:
                    merged = dict(self._shared_state)
                    merged.update(self._overrides)
                    return merged

                def keys(self):
                    return self.copy().keys()

                def items(self):
                    return self.copy().items()

                def values(self):
                    return self.copy().values()

                def __iter__(self):
                    return iter(self.copy())

                def __len__(self) -> int:
                    return len(self.copy())

                def setdefault(self, key: str, default: Any = None) -> Any:
                    if key in self:
                        return self[key]
                    self[key] = default
                    return default

            class AgentContext:
                def __init__(
                    self,
                    execution_context: ExecutionContext,
                    step_specific_overrides: dict[str, Any],
                ):
                    self.execution_context = execution_context
                    self.state = _StepStateView(execution_context.state, step_specific_overrides)

                def get(self, key: str, default: Any = None) -> Any:
                    return self.state.get(key, default)

                def keys(self):
                    return self.state.keys()

                def items(self):
                    return self.state.items()

                def values(self):
                    return self.state.values()

                def copy(self) -> dict[str, Any]:
                    return self.state.copy()

                def __getitem__(self, key: str) -> Any:
                    return self.state[key]

                def __contains__(self, key: str) -> bool:
                    return key in self.state

                def __iter__(self):
                    return iter(self.state)

                def __len__(self) -> int:
                    return len(self.state)

                def update(self, updates: dict[str, Any]) -> None:
                    self.state.update(updates)

                def update_state(self, updates: dict[str, Any]) -> None:
                    self.state.update(updates)

                def set_state_value(self, key: str, value: Any) -> None:
                    self.state[key] = value

            agent_context = AgentContext(context, mapped_overrides)

            output = self._run_agent(agent, agent_context, step.timeout_seconds)
            if not isinstance(output, dict):
                raise TypeError("Agent output must be a dict")

            # Логируем результат выполнения агента
            self._log_event(
                logging.DEBUG,
                run_id,
                "agent_execution_completed",
                step_name=step.name,
                agent=step.agent,
                output_status=output.get("status", "unknown"),
            )

            # Сначала проверяем схему с оригинальным результатом
            validation_payload = self._sanitize_output_for_validation(output)

            validation_errors = self.schema_validator.validate_step_output(
                step.name, validation_payload
            )
            if validation_errors:
                # Если есть ошибки валидации, нормализуем результат и добавляем ошибки
                normalized_output = self._normalize_agent_output(validation_payload)
                existing_errors = normalized_output.get("validation_errors", [])
                normalized_errors = (
                    list(existing_errors) if isinstance(existing_errors, list) else []
                )
                normalized_errors.extend(validation_errors)
                normalized_output["validation_errors"] = normalized_errors
                output = normalized_output
                if self.strict_schema_validation:
                    # В строгом режиме валидации возвращаем ошибку
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
                    output = self._error_result(f"Schema validation failed: {error_message}")
                else:
                    # В нестрогом режиме продолжаем с нормализованным результатом
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
                # Если ошибок валидации нет, нормализуем результат для согласованности
                output = self._normalize_agent_output(validation_payload)

            step_status = self._normalize_step_status(output.get("status"))
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
            output = self._error_result(f"Agent '{step.agent}' failed: {exc}")
            step_status = StepStatus.FAILED

        if step_status in {StepStatus.SUCCESS, StepStatus.PARTIAL_SUCCESS}:
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
