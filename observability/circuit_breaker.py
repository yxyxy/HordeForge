from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if recovery possible


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance."""

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._lock = RLock()
        self._stats = CircuitBreakerStats()
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = time.time()
        self._logger = logging.getLogger(f"hordeforge.circuit_breaker.{name}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_state_transition()
            return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        with self._lock:
            return CircuitBreakerStats(
                total_calls=self._stats.total_calls,
                successful_calls=self._stats.successful_calls,
                failed_calls=self._stats.failed_calls,
                rejected_calls=self._stats.rejected_calls,
                state=self._stats.state,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
            )

    def _check_state_transition(self) -> None:
        now = time.time()
        time_in_state = now - self._last_state_change

        if self._stats.state == CircuitState.OPEN:
            if time_in_state >= self._config.timeout_seconds:
                self._logger.info(f"Circuit {self._name}: OPEN -> HALF_OPEN")
                self._stats.state = CircuitState.HALF_OPEN
                self._last_state_change = now
                self._failure_count = 0

        elif self._stats.state == CircuitState.HALF_OPEN:
            pass  # Stay in half-open until we have enough data

    def _record_success(self) -> None:
        now = time.time()
        self._stats.successful_calls += 1
        self._stats.last_success_time = now
        self._failure_count = 0

        if self._stats.state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_threshold:
                self._logger.info(f"Circuit {self._name}: HALF_OPEN -> CLOSED")
                self._stats.state = CircuitState.CLOSED
                self._last_state_change = now
                self._success_count = 0

    def _record_failure(self) -> None:
        now = time.time()
        self._stats.failed_calls += 1
        self._stats.last_failure_time = now
        self._failure_count += 1

        if self._stats.state == CircuitState.HALF_OPEN:
            self._logger.warning(f"Circuit {self._name}: HALF_OPEN -> OPEN (test failed)")
            self._stats.state = CircuitState.OPEN
            self._last_state_change = now
            self._success_count = 0
        elif (
            self._stats.state == CircuitState.CLOSED
            and self._failure_count >= self._config.failure_threshold
        ):
            self._logger.warning(f"Circuit {self._name}: CLOSED -> OPEN (threshold reached)")
            self._stats.state = CircuitState.OPEN
            self._last_state_change = now

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            self._check_state_transition()
            self._stats.total_calls += 1

            if self._stats.state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                raise CircuitBreakerOpenError(
                    f"Circuit {self._name} is OPEN, call rejected"
                )

            if (
                self._stats.state == CircuitState.HALF_OPEN
                and self._success_count >= self._config.half_open_max_calls
            ):
                self._stats.rejected_calls += 1
                raise CircuitBreakerOpenError(
                    f"Circuit {self._name} is HALF_OPEN, max calls reached"
                )

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            raise exc

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._stats = CircuitBreakerStats()
            self._failure_count = 0
            self._success_count = 0
            self._last_state_change = time.time()


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and call is rejected."""

    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get circuit breaker by name."""
        with self._lock:
            return self._breakers.get(name)

    def list_names(self) -> list[str]:
        """List all circuit breaker names."""
        with self._lock:
            return list(self._breakers.keys())

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry instance
_circuit_breaker_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry."""
    global _circuit_breaker_registry
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry()
    return _circuit_breaker_registry
