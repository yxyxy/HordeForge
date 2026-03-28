from __future__ import annotations

from observability.load_testing import (
    BASELINE_THRESHOLDS,
    LoadTestConfig,
    LoadTestResult,
    evaluate_load_test_result,
)


def test_load_test_result_to_dict():
    """Test LoadTestResult serialization."""
    result = LoadTestResult(
        total_requests=100,
        successful_requests=95,
        failed_requests=5,
        duration_seconds=10.0,
        requests_per_second=10.0,
        latency_ms={"min": 10, "max": 100, "mean": 50, "median": 45},
        errors=["Error 1", "Error 2"],
    )
    data = result.to_dict()

    assert data["total_requests"] == 100
    assert data["successful_requests"] == 95
    assert data["failed_requests"] == 5
    assert len(data["errors"]) == 2


def test_load_tester_config():
    """Test LoadTestConfig defaults."""
    config = LoadTestConfig(target_url="http://localhost:8000")
    assert config.total_requests == 100
    assert config.concurrency == 10
    assert config.method == "POST"


def test_evaluate_load_test_result_pass():
    """Test evaluation passes when all thresholds met."""
    result = LoadTestResult(
        total_requests=100,
        successful_requests=100,
        failed_requests=0,
        duration_seconds=10.0,
        requests_per_second=15.0,
        latency_ms={"min": 10, "max": 500, "mean": 100, "median": 90, "p95": 300, "p99": 400},
    )
    evaluation = evaluate_load_test_result(result)

    assert evaluation["passed"] is True
    assert all(evaluation["checks"].values())


def test_evaluate_load_test_result_fail_throughput():
    """Test evaluation fails on low throughput."""
    result = LoadTestResult(
        total_requests=100,
        successful_requests=100,
        failed_requests=0,
        duration_seconds=10.0,
        requests_per_second=5.0,  # Below threshold
        latency_ms={"min": 10, "max": 500, "mean": 100, "median": 90, "p95": 300, "p99": 400},
    )
    evaluation = evaluate_load_test_result(result)

    assert evaluation["passed"] is False
    assert evaluation["checks"]["requests_per_second"] is False


def test_evaluate_load_test_result_fail_latency():
    """Test evaluation fails on high latency."""
    result = LoadTestResult(
        total_requests=100,
        successful_requests=100,
        failed_requests=0,
        duration_seconds=10.0,
        requests_per_second=15.0,
        latency_ms={"min": 10, "max": 5000, "mean": 2000, "median": 1500, "p95": 4000, "p99": 5000},
    )
    evaluation = evaluate_load_test_result(result)

    assert evaluation["passed"] is False
    assert evaluation["checks"]["p95_latency"] is False
    assert evaluation["checks"]["mean_latency"] is False


def test_evaluate_load_test_result_fail_errors():
    """Test evaluation fails on high error rate."""
    result = LoadTestResult(
        total_requests=100,
        successful_requests=80,
        failed_requests=20,  # 20% error rate
        duration_seconds=10.0,
        requests_per_second=15.0,
        latency_ms={"min": 10, "max": 500, "mean": 100, "median": 90, "p95": 300, "p99": 400},
    )
    evaluation = evaluate_load_test_result(result)

    assert evaluation["passed"] is False
    assert evaluation["error_rate"] == 0.2
    assert evaluation["checks"]["error_rate"] is False


def test_baseline_thresholds_exist():
    """Test baseline thresholds are defined."""
    assert "min_requests_per_second" in BASELINE_THRESHOLDS
    assert "max_p95_latency_ms" in BASELINE_THRESHOLDS
    assert "max_error_rate" in BASELINE_THRESHOLDS
    assert "max_mean_latency_ms" in BASELINE_THRESHOLDS
