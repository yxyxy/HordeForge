from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, TypeVar, overload

from orchestrator.hooks import ExecutionGuardrailHook
from orchestrator.retry import RetryPolicy
from orchestrator.summary import RunSummaryBuilder
from orchestrator.validation import RuntimeSchemaValidator

T = TypeVar("T")


@dataclass
class OrchestratorDependencies:
    """Typed registry of all dependencies needed by the orchestrator.

    Each field is optional and can be provided by the caller or resolved
    lazily by the container via factory callables.
    """

    pipeline_loader: Any = None
    step_executor: Any = None
    pipeline_runner: Any = None
    retry_policy: RetryPolicy | None = None
    execution_guardrail_hook: ExecutionGuardrailHook | None = None
    summary_builder: RunSummaryBuilder | None = None
    state_validator: RuntimeSchemaValidator | None = None
    pipeline_validator: Any = None
    agent_registry: Any = None
    pipeline_registry: Any = None
    contract_registry: Any = None
    rule_pack_loader: Any = None
    checkpoint_lock: RLock = field(default_factory=RLock)
    logger: logging.Logger | None = None


class DependencyContainer:
    """Lightweight DI container for orchestrator dependencies.

    Supports three resolution modes:
    1. Direct binding: container.bind(RetryPolicy, my_policy)
    2. Factory binding: container.register_factory(RetryPolicy, lambda: my_policy)
    3. Fallback to default construction via a resolver callable
    """

    def __init__(self) -> None:
        self._bindings: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._lock = RLock()

    def bind(self, abstraction: type, instance: Any) -> None:
        """Bind a concrete instance to an abstraction type."""
        with self._lock:
            self._bindings[abstraction] = instance
            self._factories.pop(abstraction, None)

    def register_factory(self, abstraction: type, factory: Callable[[], Any]) -> None:
        """Register a lazy factory. Instance is created on first resolve."""
        with self._lock:
            self._factories[abstraction] = factory

    def resolve(self, abstraction: type) -> Any | None:
        """Resolve a single dependency. Returns None if unregistered."""
        with self._lock:
            if abstraction in self._bindings:
                return self._bindings[abstraction]
            if abstraction in self._factories:
                instance = self._factories[abstraction]()
                self._bindings[abstraction] = instance
                del self._factories[abstraction]
                return instance
        return None

    def has(self, abstraction: type) -> bool:
        with self._lock:
            return abstraction in self._bindings or abstraction in self._factories

    @overload
    def resolve_or_default(self, abstraction: type, default: T) -> T: ...

    @overload
    def resolve_or_default(self, abstraction: type, default: None = None) -> Any | None: ...

    def resolve_or_default(self, abstraction: type, default: Any = None) -> Any:
        """Resolve with a fallback default."""
        result = self.resolve(abstraction)
        return result if result is not None else default

    def clear(self) -> None:
        """Remove all bindings and factories."""
        with self._lock:
            self._bindings.clear()
            self._factories.clear()
