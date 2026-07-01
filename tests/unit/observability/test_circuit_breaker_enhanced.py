from __future__ import annotations

import time

import pytest

from observability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)


class TestIgnoreExceptions:
    def test_ignored_exceptions_do_not_trip_breaker(self):
        cb = CircuitBreaker(
            "test-ignore",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout_seconds=60,
                ignore_exceptions=(ValueError,),
            ),
        )

        def raises_value_error():
            raise ValueError("ignored")

        for _ in range(10):
            with pytest.raises(ValueError):
                cb.call(raises_value_error)

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failed_calls == 0
        assert cb.stats.total_calls == 10

    def test_normal_exceptions_still_trip_breaker(self):
        cb = CircuitBreaker(
            "test-normal",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout_seconds=60,
                ignore_exceptions=(ValueError,),
            ),
        )

        def raises_type_error():
            raise TypeError("not ignored")

        for _ in range(3):
            with pytest.raises(TypeError):
                cb.call(raises_type_error)

        assert cb.state == CircuitState.OPEN

    def test_mixed_exceptions_only_count_non_ignored(self):
        cb = CircuitBreaker(
            "test-mixed",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout_seconds=60,
                ignore_exceptions=(ValueError,),
            ),
        )
        call_count = 0

        def raises_mixed():
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ValueError("ignored")
            raise RuntimeError("counted")

        for _ in range(5):
            with pytest.raises((ValueError, RuntimeError)):
                cb.call(raises_mixed)

        assert cb.state == CircuitState.OPEN
        assert cb.stats.failed_calls == 3

    def test_multiple_ignore_exception_types(self):
        cb = CircuitBreaker(
            "test-multi-ignore",
            CircuitBreakerConfig(
                failure_threshold=2,
                timeout_seconds=60,
                ignore_exceptions=(ValueError, KeyError, IOError),
            ),
        )

        def raises_key_error():
            raise KeyError("ignored")

        for _ in range(10):
            with pytest.raises(KeyError):
                cb.call(raises_key_error)

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failed_calls == 0

    def test_ignored_exception_still_records_total_calls(self):
        cb = CircuitBreaker(
            "test-total",
            CircuitBreakerConfig(
                failure_threshold=5,
                timeout_seconds=60,
                ignore_exceptions=(ValueError,),
            ),
        )

        def raises_value_error():
            raise ValueError("ignored")

        for _ in range(7):
            with pytest.raises(ValueError):
                cb.call(raises_value_error)

        assert cb.stats.total_calls == 7
        assert cb.stats.failed_calls == 0
        assert cb.state == CircuitState.CLOSED


class TestHalfOpenWithIgnoreExceptions:
    def test_half_open_ignored_exception_does_not_reopen(self):
        cb = CircuitBreaker(
            "test-half-ignore",
            CircuitBreakerConfig(
                failure_threshold=1,
                success_threshold=2,
                timeout_seconds=0.1,
                ignore_exceptions=(ValueError,),
            ),
        )

        def failing_func():
            raise RuntimeError("real failure")

        with pytest.raises(RuntimeError):
            cb.call(failing_func)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        def ignored_in_half_open():
            raise ValueError("ignored in half-open")

        for _ in range(5):
            with pytest.raises(ValueError):
                cb.call(ignored_in_half_open)

        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_real_failure_reopens_circuit(self):
        cb = CircuitBreaker(
            "test-half-fail",
            CircuitBreakerConfig(
                failure_threshold=1,
                success_threshold=2,
                timeout_seconds=0.1,
                ignore_exceptions=(ValueError,),
            ),
        )

        def failing_func():
            raise RuntimeError("real failure")

        with pytest.raises(RuntimeError):
            cb.call(failing_func)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            cb.call(failing_func)

        assert cb.state == CircuitState.OPEN


class TestCallRecordsSuccessAndFailure:
    def test_successful_call_records_stats(self):
        cb = CircuitBreaker("test-success", CircuitBreakerConfig(failure_threshold=3))

        result = cb.call(lambda: 42)

        assert result == 42
        assert cb.stats.successful_calls == 1
        assert cb.stats.failed_calls == 0
        assert cb.stats.total_calls == 1

    def test_failed_call_records_stats(self):
        cb = CircuitBreaker("test-fail-stats", CircuitBreakerConfig(failure_threshold=3))

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("boom")))

        assert cb.stats.failed_calls == 1
        assert cb.stats.successful_calls == 0
        assert cb.stats.total_calls == 1

    def test_rejected_call_records_stats(self):
        cb = CircuitBreaker(
            "test-reject-stats",
            CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60),
        )

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("boom")))

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not run")

        assert cb.stats.rejected_calls == 1
        assert cb.stats.total_calls == 2

    def test_call_passes_args_and_kwargs(self):
        cb = CircuitBreaker("test-args", CircuitBreakerConfig(failure_threshold=3))

        def add(a, b, extra=0):
            return a + b + extra

        result = cb.call(add, 1, 2, extra=10)
        assert result == 13


class TestStateTransitions:
    def test_closed_to_open(self):
        cb = CircuitBreaker("test-co", CircuitBreakerConfig(failure_threshold=2))

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("1")))
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("2")))

        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open(self):
        cb = CircuitBreaker(
            "test-oh",
            CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1),
        )

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed(self):
        cb = CircuitBreaker(
            "test-hc",
            CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=0.1),
        )

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.call(lambda: "ok1")
        assert cb.state == CircuitState.HALF_OPEN
        cb.call(lambda: "ok2")
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(
            "test-ho",
            CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=0.1),
        )

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail again")))

        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test-reset", CircuitBreakerConfig(failure_threshold=3))

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        cb.call(lambda: "recovery")

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failed_calls == 2
