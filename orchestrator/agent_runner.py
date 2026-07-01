from __future__ import annotations

import asyncio
import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from threading import RLock
from typing import Any

from orchestrator.context import ExecutionContext
from registry.agents import AgentMetadata, AgentRegistry  # noqa: F401

logger = logging.getLogger("hordeforge.orchestrator.agent_runner")


def invoke_agent_run(agent: Any, payload: Any) -> Any:
    """Invoke an agent's run method with the given payload, handling signature introspection."""
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


def run_agent(agent: Any, payload: Any, timeout_seconds: float | None) -> dict[str, Any]:
    """Run an agent with optional timeout, handling async results."""

    def invoke_with_await_support() -> dict[str, Any]:
        result = invoke_agent_run(agent, payload)
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
            future.cancel()
            raise TimeoutError(f"Step timed out after {timeout_seconds} seconds") from exc


class DynamicRegistryWrapper:
    """Wraps a base registry and delegates to a factory for unknown agents."""

    def __init__(self, base_reg: Any, factory_func: Any) -> None:
        self.base_registry = base_reg
        self.factory = factory_func
        self.dynamic_agents: dict[str, Any] = {}

    def has(self, agent_name: str) -> bool:
        if self.base_registry.has(agent_name):
            return True

        try:
            agent = self.factory(agent_name)
            self.dynamic_agents[agent_name] = agent.__class__
            return True
        except Exception as e:
            logger.debug("Dynamic agent factory failed for %s: %s", agent_name, e)
            return False

    def create(self, agent_name: str) -> Any:
        if self.base_registry.has(agent_name):
            return self.base_registry.create(agent_name)

        agent = self.factory(agent_name)
        return agent

    def get(self, agent_name: str) -> Any:
        if self.base_registry.has(agent_name):
            item = self.base_registry.get(agent_name)
            if isinstance(item, AgentMetadata):
                return item.agent_class
            return item

        if agent_name in self.dynamic_agents:
            return self.dynamic_agents[agent_name]

        try:
            agent = self.factory(agent_name)
            self.dynamic_agents[agent_name] = agent.__class__
            return agent.__class__
        except Exception as e:
            logger.debug("Dynamic agent factory failed for %s: %s", agent_name, e)
            raise KeyError(f"Agent '{agent_name}' is not registered") from None


def create_registry_from_factory(base_registry: Any, factory: Any) -> DynamicRegistryWrapper:
    """Create a dynamic registry that delegates to factory for unknown agents."""
    return DynamicRegistryWrapper(base_registry, factory)


class StepStateView:
    """A view over shared state with per-step overrides. Supports dict-like access."""

    def __init__(
        self,
        shared_state: dict[str, Any],
        overrides: dict[str, Any],
        lock: RLock | None = None,
    ) -> None:
        self._shared_state = shared_state
        self._overrides = dict(overrides)
        self._lock = lock

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._shared_state.get(key, default)

    def __getitem__(self, key: str) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._shared_state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if self._lock:
            with self._lock:
                self._shared_state[key] = value
                self._overrides[key] = value
        else:
            self._shared_state[key] = value
            self._overrides[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._overrides or key in self._shared_state

    def update(self, updates: dict[str, Any]) -> None:
        if self._lock:
            with self._lock:
                self._shared_state.update(updates)
                self._overrides.update(updates)
        else:
            self._shared_state.update(updates)
            self._overrides.update(updates)

    def copy(self) -> dict[str, Any]:
        merged = dict(self._shared_state)
        merged.update(self._overrides)
        return merged

    def keys(self):  # noqa: ANN201
        return self.copy().keys()

    def items(self):  # noqa: ANN201
        return self.copy().items()

    def values(self):  # noqa: ANN201
        return self.copy().values()

    def __iter__(self):  # noqa: ANN205
        return iter(self.copy())

    def __len__(self) -> int:
        return len(self.copy())

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default


class AgentContext:
    """Context provided to agents, wrapping an execution context with step-specific overrides."""

    def __init__(
        self,
        execution_context: ExecutionContext,
        step_specific_overrides: dict[str, Any],
    ) -> None:
        self.execution_context = execution_context
        self.state = StepStateView(
            execution_context.state, step_specific_overrides, execution_context._lock
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def keys(self):  # noqa: ANN201
        return self.state.keys()

    def items(self):  # noqa: ANN201
        return self.state.items()

    def values(self):  # noqa: ANN201
        return self.state.values()

    def copy(self) -> dict[str, Any]:
        return self.state.copy()

    def __getitem__(self, key: str) -> Any:
        return self.state[key]

    def __contains__(self, key: str) -> bool:
        return key in self.state

    def __iter__(self):  # noqa: ANN205
        return iter(self.state)

    def __len__(self) -> int:
        return len(self.state)

    def update(self, updates: dict[str, Any]) -> None:
        self.state.update(updates)

    def update_state(self, updates: dict[str, Any]) -> None:
        self.state.update(updates)

    def set_state_value(self, key: str, value: Any) -> None:
        self.state[key] = value
