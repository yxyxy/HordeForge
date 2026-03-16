from __future__ import annotations

import json
import logging
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
                    self.dynamic_agents[agent_name] = lambda: agent
                    return True
                except Exception:
                    return False

            def create(self, agent_name: str) -> Any:
                # Если агент в базовом реестре - используем его
                if self.base_registry.has(agent_name):
                    return self.base_registry.create(agent_name)

                # Если агент был создан ранее через фабрику - используем кэшированную версию
                if agent_name in self.dynamic_agents:
                    return self.dynamic_agents[agent_name]()

                # Иначе создаем через фабрику и кэшируем
                agent = self.factory(agent_name)
                self.dynamic_agents[agent_name] = lambda: agent
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
                    agent_instance = self.dynamic_agents[agent_name]()
                    return agent_instance.__class__

                # Если агент не существует, пробуем создать через фабрику
                try:
                    agent = self.factory(agent_name)
                    self.dynamic_agents[agent_name] = lambda: agent
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
    def _run_agent(
        agent: Any, payload: dict[str, Any], timeout_seconds: float | None
    ) -> dict[str, Any]:
        import asyncio
        import inspect

        # Check if agent.run is a coroutine (async method)
        if inspect.iscoroutinefunction(agent.run):
            if timeout_seconds is None:
                return asyncio.run(agent.run(payload))
            else:
                # For async agents with timeout, run in event loop with timeout
                async def run_with_timeout():
                    return await asyncio.wait_for(
                        agent.run(payload),
                        timeout=timeout_seconds,
                    )

                return asyncio.run(run_with_timeout())

        # Synchronous agent
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
            # Всегда получаем агент через реестр, без возможности прямого создания
            agent = self._get_agent_from_registry(step.agent, run_id)
            output = self._run_agent(agent, context.state, step.timeout_seconds)
            if not isinstance(output, dict):
                raise TypeError("Agent output must be a dict")

            # Сначала проверяем схему с оригинальным результатом
            validation_errors = self.schema_validator.validate_step_output(step.name, output)
            if validation_errors:
                # Если есть ошибки валидации, нормализуем результат и добавляем ошибки
                normalized_output = self._normalize_agent_output(output)
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
                output = self._normalize_agent_output(output)

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
