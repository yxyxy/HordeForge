from __future__ import annotations

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class LoadTestResult:
    """Result of a load test."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    requests_per_second: float
    latency_ms: dict[str, float]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "duration_seconds": self.duration_seconds,
            "requests_per_second": self.requests_per_second,
            "latency_ms": self.latency_ms,
            "errors": self.errors,
        }


@dataclass
class LoadTestConfig:
    """Configuration for load test."""

    target_url: str
    total_requests: int = 100
    concurrency: int = 10
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] | None = None
    timeout_seconds: float = 30.0


class LoadTester:
    """Load testing utility for HordeForge."""

    def __init__(self, config: LoadTestConfig) -> None:
        self._config = config
        self._results: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def _make_request(self, request_id: int) -> dict[str, Any]:
        """Make a single HTTP request."""
        import urllib.error
        import urllib.request

        start_time = time.time()
        result = {
            "request_id": request_id,
            "success": False,
            "latency_ms": 0,
            "error": None,
            "status_code": None,
        }

        try:
            if urlparse(self._config.target_url).scheme.lower() not in {"http", "https"}:
                result["error"] = "Unsupported URL scheme"
                return result

            data = None
            if self._config.payload:
                data = json.dumps(self._config.payload).encode("utf-8")

            headers = dict(self._config.headers)
            if data:
                headers["Content-Type"] = "application/json"

            req = urllib.request.Request(
                self._config.target_url,
                data=data,
                headers=headers,
                method=self._config.method,
            )

            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as response:  # nosec B310
                result["status_code"] = response.status
                result["success"] = 200 <= response.status < 300

        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP {e.code}: {e.reason}"
            result["status_code"] = e.code
        except urllib.error.URLError as e:
            result["error"] = f"URL Error: {e.reason}"
        except Exception as e:
            result["error"] = str(e)

        result["latency_ms"] = (time.time() - start_time) * 1000

        with self._lock:
            self._results.append(result)

        return result

    def run(self) -> LoadTestResult:
        """Run load test."""
        self._results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self._config.concurrency) as executor:
            futures = [
                executor.submit(self._make_request, i) for i in range(self._config.total_requests)
            ]

            for future in as_completed(futures):
                future.result()  # Wait for completion

        duration = time.time() - start_time
        return self._analyze_results(duration)

    def _analyze_results(self, duration: float) -> LoadTestResult:
        """Analyze test results."""
        latencies = [r["latency_ms"] for r in self._results]
        errors = [r["error"] for r in self._results if r["error"]]

        successful = sum(1 for r in self._results if r["success"])
        failed = len(self._results) - successful

        return LoadTestResult(
            total_requests=len(self._results),
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=duration,
            requests_per_second=len(self._results) / duration if duration > 0 else 0,
            latency_ms={
                "min": min(latencies) if latencies else 0,
                "max": max(latencies) if latencies else 0,
                "mean": statistics.mean(latencies) if latencies else 0,
                "median": statistics.median(latencies) if latencies else 0,
                "p95": self._percentile(latencies, 95) if latencies else 0,
                "p99": self._percentile(latencies, 99) if latencies else 0,
            },
            errors=errors[:10],  # Limit to first 10 errors
        )

    @staticmethod
    def _percentile(data: list[float], percentile: int) -> float:
        """Calculate percentile."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


def run_load_test(
    target_url: str,
    total_requests: int = 100,
    concurrency: int = 10,
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> LoadTestResult:
    """Convenience function to run load test."""
    headers = {}
    if api_key:
        headers["X-Operator-Key"] = api_key

    config = LoadTestConfig(
        target_url=target_url,
        total_requests=total_requests,
        concurrency=concurrency,
        payload=payload,
        headers=headers,
    )

    tester = LoadTester(config)
    return tester.run()


# Baseline thresholds for 1000 runs/day
BASELINE_THRESHOLDS = {
    "min_requests_per_second": 10.0,  # ~864k/day at max
    "max_p95_latency_ms": 3000.0,  # 3 seconds p95
    "max_error_rate": 0.05,  # 5% max errors
    "max_mean_latency_ms": 1000.0,  # 1 second mean
}


def evaluate_load_test_result(result: LoadTestResult) -> dict[str, Any]:
    """Evaluate load test against baseline thresholds."""
    error_rate = result.failed_requests / result.total_requests if result.total_requests > 0 else 0

    passed = {
        "requests_per_second": result.requests_per_second
        >= BASELINE_THRESHOLDS["min_requests_per_second"],
        "p95_latency": result.latency_ms["p95"] <= BASELINE_THRESHOLDS["max_p95_latency_ms"],
        "error_rate": error_rate <= BASELINE_THRESHOLDS["max_error_rate"],
        "mean_latency": result.latency_ms["mean"] <= BASELINE_THRESHOLDS["max_mean_latency_ms"],
    }

    all_passed = all(passed.values())

    return {
        "passed": all_passed,
        "checks": passed,
        "error_rate": error_rate,
        "total_requests": result.total_requests,
        "recommendations": _get_recommendations(passed, result),
    }


def _get_recommendations(passed: dict[str, bool], result: LoadTestResult) -> list[str]:
    """Generate recommendations based on test results."""
    recommendations = []

    if not passed["requests_per_second"]:
        recommendations.append(
            f"Throughput too low: {result.requests_per_second:.1f} req/s. "
            "Consider horizontal scaling or queue optimization."
        )

    if not passed["p95_latency"]:
        recommendations.append(
            f"High p95 latency: {result.latency_ms['p95']:.0f}ms. "
            "Consider adding caching or optimizing slow endpoints."
        )

    if not passed["error_rate"]:
        error_rate = (
            result.failed_requests / result.total_requests if result.total_requests > 0 else 0
        )
        recommendations.append(
            f"High error rate: {error_rate * 100:.1f}%. Review error logs and fix stability issues."
        )

    if not passed["mean_latency"]:
        recommendations.append(
            f"High mean latency: {result.latency_ms['mean']:.0f}ms. "
            "Profile and optimize database queries and API calls."
        )

    if not recommendations:
        recommendations.append("All baseline checks passed!")

    return recommendations
