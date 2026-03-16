"""Agent quality benchmarks (HF-P5-009).

This module provides benchmarking and metrics collection for agent quality.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentMetrics:
    """Metrics for a single agent run."""

    agent_name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    success: bool = False
    error: str | None = None

    # Quality metrics
    spec_accuracy: float = 0.0  # 0-1: did spec lead to working code
    code_pass_rate: float = 0.0  # 0-1: did code work on first try
    test_coverage: float = 0.0  # 0-1: percentage of code covered
    fix_iterations: int = 0  # How many attempts to fix
    latency_seconds: float = 0.0

    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    benchmark_name: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    # Aggregated metrics
    avg_spec_accuracy: float = 0.0
    avg_code_pass_rate: float = 0.0
    avg_test_coverage: float = 0.0
    avg_fix_iterations: float = 0.0
    avg_latency_seconds: float = 0.0

    # Percentiles
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0

    # Score (0-100)
    overall_score: float = 0.0


class AgentBenchmarkCollector:
    """Collects and aggregates agent quality metrics."""

    def __init__(self):
        self._metrics: list[AgentMetrics] = []

    def record_run(self, metrics: AgentMetrics) -> None:
        """Record a single agent run."""
        self._metrics.append(metrics)

    def get_metrics(self, agent_name: str | None = None) -> list[AgentMetrics]:
        """Get metrics for a specific agent or all agents."""
        if agent_name:
            return [m for m in self._metrics if m.agent_name == agent_name]
        return self._metrics.copy()

    def compute_benchmark(self, agent_name: str) -> BenchmarkResult:
        """Compute benchmark statistics for an agent."""
        agent_metrics = self.get_metrics(agent_name)

        if not agent_metrics:
            return BenchmarkResult(benchmark_name=agent_name)

        total = len(agent_metrics)
        successful = sum(1 for m in agent_metrics if m.success)
        failed = total - successful

        # Calculate averages
        avg_spec_accuracy = sum(m.spec_accuracy for m in agent_metrics) / total
        avg_code_pass_rate = sum(m.code_pass_rate for m in agent_metrics) / total
        avg_test_coverage = sum(m.test_coverage for m in agent_metrics) / total
        avg_fix_iterations = sum(m.fix_iterations for m in agent_metrics) / total
        avg_latency = sum(m.latency_seconds for m in agent_metrics) / total

        # Calculate percentiles for latency
        latencies = sorted(m.latency_seconds for m in agent_metrics)
        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        p99 = _percentile(latencies, 99)

        # Calculate overall score (0-100)
        score = (
            avg_spec_accuracy * 25
            + avg_code_pass_rate * 25
            + avg_test_coverage * 25
            + (1.0 - min(avg_fix_iterations / 5.0, 1.0)) * 25
        )

        return BenchmarkResult(
            benchmark_name=agent_name,
            total_runs=total,
            successful_runs=successful,
            failed_runs=failed,
            avg_spec_accuracy=avg_spec_accuracy,
            avg_code_pass_rate=avg_code_pass_rate,
            avg_test_coverage=avg_test_coverage,
            avg_fix_iterations=avg_fix_iterations,
            avg_latency_seconds=avg_latency,
            p50_latency=p50,
            p95_latency=p95,
            p99_latency=p99,
            overall_score=score,
        )

    def get_all_benchmarks(self) -> dict[str, BenchmarkResult]:
        """Get benchmarks for all agents."""
        agent_names = set(m.agent_name for m in self._metrics)
        return {name: self.compute_benchmark(name) for name in agent_names}

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()


def _percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile of a list."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int((percentile / 100.0) * len(sorted_vals))
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[max(0, idx)]


# Default baseline thresholds
BASELINE_THRESHOLDS = {
    "spec_accuracy": 0.85,
    "code_pass_rate": 0.80,
    "test_coverage": 0.70,
    "fix_iterations": 2.0,
    "latency_p95_seconds": 30.0,
}


def check_baseline(
    result: BenchmarkResult,
    thresholds: dict[str, float] | None = None,
) -> dict[str, bool]:
    """Check if benchmark meets baseline thresholds."""
    thresholds = thresholds or BASELINE_THRESHOLDS

    return {
        "spec_accuracy": result.avg_spec_accuracy >= thresholds.get("spec_accuracy", 0.85),
        "code_pass_rate": result.avg_code_pass_rate >= thresholds.get("code_pass_rate", 0.80),
        "test_coverage": result.avg_test_coverage >= thresholds.get("test_coverage", 0.70),
        "fix_iterations": result.avg_fix_iterations <= thresholds.get("fix_iterations", 2.0),
        "latency": result.p95_latency <= thresholds.get("latency_p95_seconds", 30.0),
    }


def format_benchmark_report(result: BenchmarkResult) -> str:
    """Format benchmark result as a readable report."""
    checks = check_baseline(result)
    status = "✅ PASS" if all(checks.values()) else "⚠️ REGRESSION"

    return f"""
# Agent Quality Benchmark: {result.benchmark_name}
Generated: {result.timestamp}

## Summary
- **Status**: {status}
- **Overall Score**: {result.overall_score:.1f}/100
- **Total Runs**: {result.total_runs}
- **Success Rate**: {result.successful_runs}/{result.total_runs} ({result.successful_runs / result.total_runs * 100:.1f}%)

## Quality Metrics
| Metric | Value | Baseline | Status |
|--------|-------|----------|--------|
| Spec Accuracy | {result.avg_spec_accuracy:.1%} | 85% | {"✅" if checks["spec_accuracy"] else "❌"} |
| Code Pass Rate | {result.avg_code_pass_rate:.1%} | 80% | {"✅" if checks["code_pass_rate"] else "❌"} |
| Test Coverage | {result.avg_test_coverage:.1%} | 70% | {"✅" if checks["test_coverage"] else "❌"} |
| Avg Fix Iterations | {result.avg_fix_iterations:.1f} | ≤2 | {"✅" if checks["fix_iterations"] else "❌"} |

## Latency
| Percentile | Value |
|------------|-------|
| p50 | {result.p50_latency:.2f}s |
| p95 | {result.p95_latency:.2f}s |
| p99 | {result.p99_latency:.2f}s |
"""


# Golden set of test issues for benchmarking
GOLDEN_TEST_ISSUES = [
    {
        "id": "issue_001",
        "title": "Add user authentication",
        "language": "python",
        "complexity": "medium",
    },
    {
        "id": "issue_002",
        "title": "Create REST API endpoint",
        "language": "python",
        "complexity": "medium",
    },
    {
        "id": "issue_003",
        "title": "Add unit tests for utils",
        "language": "python",
        "complexity": "low",
    },
    {
        "id": "issue_004",
        "title": "Implement data migration script",
        "language": "python",
        "complexity": "high",
    },
    {
        "id": "issue_005",
        "title": "Add React component",
        "language": "typescript",
        "complexity": "medium",
    },
    {
        "id": "issue_006",
        "title": "Create Go HTTP handler",
        "language": "go",
        "complexity": "medium",
    },
    {"id": "issue_007", "title": "Fix memory leak", "language": "python", "complexity": "high"},
    {"id": "issue_008", "title": "Add input validation", "language": "python", "complexity": "low"},
    {
        "id": "issue_009",
        "title": "Implement caching layer",
        "language": "python",
        "complexity": "medium",
    },
    {"id": "issue_010", "title": "Add error handling", "language": "python", "complexity": "low"},
]


# Scoring rubrics
SCORING_RUBRIC = {
    "spec_accuracy": {
        "excellent": (0.9, 25),
        "good": (0.8, 20),
        "acceptable": (0.7, 15),
        "poor": (0.0, 0),
    },
    "code_pass_rate": {
        "excellent": (0.9, 25),
        "good": (0.8, 20),
        "acceptable": (0.7, 15),
        "poor": (0.0, 0),
    },
    "test_coverage": {
        "excellent": (0.8, 25),
        "good": (0.7, 20),
        "acceptable": (0.6, 15),
        "poor": (0.0, 0),
    },
    "fix_efficiency": {
        "excellent": (1, 25),  # 1 iteration
        "good": (2, 20),
        "acceptable": (3, 15),
        "poor": (10, 0),
    },
}


def calculate_score(
    spec_accuracy: float,
    code_pass_rate: float,
    test_coverage: float,
    fix_iterations: int,
) -> float:
    """Calculate overall score (0-100) based on metrics."""
    score = 0.0

    # Spec accuracy (25 points)
    if spec_accuracy >= 0.9:
        score += 25
    elif spec_accuracy >= 0.8:
        score += 20
    elif spec_accuracy >= 0.7:
        score += 15

    # Code pass rate (25 points)
    if code_pass_rate >= 0.9:
        score += 25
    elif code_pass_rate >= 0.8:
        score += 20
    elif code_pass_rate >= 0.7:
        score += 15

    # Test coverage (25 points)
    if test_coverage >= 0.8:
        score += 25
    elif test_coverage >= 0.7:
        score += 20
    elif test_coverage >= 0.6:
        score += 15

    # Fix efficiency (25 points)
    if fix_iterations <= 1:
        score += 25
    elif fix_iterations <= 2:
        score += 20
    elif fix_iterations <= 3:
        score += 15

    return score


# Singleton instance for global use
_default_collector: AgentBenchmarkCollector | None = None


def get_default_collector() -> AgentBenchmarkCollector:
    """Get the default benchmark collector instance."""
    global _default_collector
    if _default_collector is None:
        _default_collector = AgentBenchmarkCollector()
    return _default_collector
