from __future__ import annotations

import time

import pytest

from observability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_circuit_breaker_registry,
)


def test_circuit_breaker_closed_state():
    """Test circuit breaker starts in closed state."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens after failure threshold."""
    cb = CircuitBreaker(
        "test-fail", CircuitBreakerConfig(failure_threshold=3, timeout_seconds=60)
    )

    def failing_func():
        raise ValueError("failure")

    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(failing_func)

    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_rejects_calls_when_open():
    """Test circuit breaker rejects calls when open."""
    cb = CircuitBreaker(
        "test-reject", CircuitBreakerConfig(failure_threshold=2, timeout_seconds=60)
    )

    def failing_func():
        raise ValueError("failure")

    # Trigger failure threshold
    with pytest.raises(ValueError):
        cb.call(failing_func)
    with pytest.raises(ValueError):
        cb.call(failing_func)

    # Now should reject
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(lambda: "success")


def test_circuit_breaker_half_open_after_timeout():
    """Test circuit breaker transitions to half-open after timeout."""
    cb = CircuitBreaker(
        "test-timeout",
        CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1),
    )

    def failing_func():
        raise ValueError("failure")

    with pytest.raises(ValueError):
        cb.call(failing_func)
    assert cb.state == CircuitState.OPEN

    # Wait for timeout
    time.sleep(0.2)
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_recovers():
    """Test circuit breaker recovers after success in half-open."""
    cb = CircuitBreaker(
        "test-recover",
        CircuitBreakerConfig(
            failure_threshold=1, success_threshold=2, timeout_seconds=0.1
        ),
    )

    def failing_func():
        raise ValueError("failure")

    with pytest.raises(ValueError):
        cb.call(failing_func)  # Opens circuit
    time.sleep(0.2)  # Wait for half-open

    # Success in half-open
    cb.call(lambda: "success")
    assert cb.state == CircuitState.HALF_OPEN

    cb.call(lambda: "success")  # Second success closes circuit
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_stats():
    """Test circuit breaker tracks stats correctly."""
    cb = CircuitBreaker("test-stats", CircuitBreakerConfig(failure_threshold=5))

    cb.call(lambda: "success")
    cb.call(lambda: "success")

    stats = cb.stats
    assert stats.total_calls == 2
    assert stats.successful_calls == 2
    assert stats.failed_calls == 0


def test_circuit_breaker_registry():
    """Test circuit breaker registry."""
    registry = get_circuit_breaker_registry()

    cb1 = registry.get_or_create("test-1")
    cb2 = registry.get_or_create("test-1")  # Same instance
    cb3 = registry.get_or_create("test-2")

    assert cb1 is cb2
    assert cb1 is not cb3
    assert "test-1" in registry.list_names()
    assert "test-2" in registry.list_names()


def test_circuit_breaker_reset():
    """Test circuit breaker reset."""
    cb = CircuitBreaker(
        "test-reset", CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
    )

    def failing_func():
        raise ValueError("failure")

    with pytest.raises(ValueError):
        cb.call(failing_func)
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    stats = cb.stats
    assert stats.total_calls == 0
