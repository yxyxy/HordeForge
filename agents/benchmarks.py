"""Agent quality benchmarks - measures and tracks agent performance."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BenchmarkResult:
    name: str
    score: float  # 0.0 to 1.0
    duration_ms: int
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now)
    error: str | None = None


@dataclass
class AgentBenchmark:
    agent_name: str
    version: str
    results: list[BenchmarkResult] = field(default_factory=list)
    overall_score: float = 0.0
    run_at: str = field(default_factory=_utc_now)

    def calculate_overall_score(self) -> float:
        """Calculate overall score from all results."""
        if not self.results:
            return 0.0

        total_score = sum(r.score for r in self.results)
        self.overall_score = total_score / len(self.results)
        return self.overall_score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_name": self.agent_name,
            "version": self.version,
            "overall_score": self.overall_score,
            "run_at": self.run_at,
            "results": [
                {
                    "name": r.name,
                    "score": r.score,
                    "duration_ms": r.duration_ms,
                    "passed": r.passed,
                    "metrics": r.metrics,
                    "timestamp": r.timestamp,
                    "error": r.error,
                }
                for r in self.results
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentBenchmark:
        """Create from dictionary."""
        benchmark = cls(
            agent_name=data["agent_name"],
            version=data["version"],
            overall_score=data.get("overall_score", 0.0),
            run_at=data.get("run_at", datetime.now(timezone.utc).isoformat()),
        )

        for result_data in data.get("results", []):
            benchmark.results.append(
                BenchmarkResult(
                    name=result_data["name"],
                    score=result_data["score"],
                    duration_ms=result_data["duration_ms"],
                    passed=result_data["passed"],
                    metrics=result_data.get("metrics", {}),
                    timestamp=result_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    error=result_data.get("error"),
                )
            )

        return benchmark


class BenchmarkRegistry:
    """Registry for benchmark definitions and results."""

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path = (
            Path(storage_path) if storage_path else Path(".hordeforge_data/benchmarks")
        )
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.benchmarks: dict[str, AgentBenchmark] = {}

    def register_benchmark(self, benchmark: AgentBenchmark) -> None:
        """Register a benchmark result."""
        key = f"{benchmark.agent_name}_{benchmark.version}_{benchmark.run_at}"
        self.benchmarks[key] = benchmark

        self._save_benchmark(benchmark, key)

    def _save_benchmark(self, benchmark: AgentBenchmark, key: str) -> None:
        """Save benchmark to file."""
        safe_key = key.replace(":", "-").replace(" ", "_")
        file_path = self.storage_path / f"{safe_key}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(benchmark.to_dict(), f, indent=2)

    def load_benchmark(self, agent_name: str, version: str) -> list[AgentBenchmark]:
        """Load all benchmarks for an agent."""
        results = []
        pattern = f"{agent_name}_{version}_*.json"

        for file_path in self.storage_path.glob(pattern):
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                results.append(AgentBenchmark.from_dict(data))

        return sorted(results, key=lambda x: x.run_at, reverse=True)

    def get_latest_benchmark(self, agent_name: str, version: str) -> AgentBenchmark | None:
        """Get the latest benchmark for an agent."""
        benchmarks = self.load_benchmark(agent_name, version)
        return benchmarks[0] if benchmarks else None

    def compare_versions(self, agent_name: str, version1: str, version2: str) -> dict[str, Any]:
        """Compare two versions of an agent."""
        bench1 = self.get_latest_benchmark(agent_name, version1)
        bench2 = self.get_latest_benchmark(agent_name, version2)

        if not bench1 or not bench2:
            return {"error": "One or both versions not found"}

        return {
            "agent_name": agent_name,
            "version1": version1,
            "version2": version2,
            "score1": bench1.overall_score,
            "score2": bench2.overall_score,
            "improvement": bench2.overall_score - bench1.overall_score,
            "improvement_percent": (
                (bench2.overall_score - bench1.overall_score) / bench1.overall_score * 100
                if bench1.overall_score > 0
                else 0
            ),
        }

    def save_benchmark(self, benchmark: AgentBenchmark) -> None:
        """Save a benchmark to the registry."""
        key = f"{benchmark.agent_name}_{benchmark.version}_{benchmark.run_at}"
        self._save_benchmark(benchmark, key)


class BenchmarkRunner:
    """Runs benchmarks for agents."""

    def __init__(self, registry: BenchmarkRegistry | None = None) -> None:
        self.registry = registry or BenchmarkRegistry()
        self.logger = logging.getLogger("hordeforge.benchmarks")

    def run_benchmark(
        self,
        agent_name: str,
        version: str,
        test_cases: list[dict[str, Any]],
        runner_func: callable,
    ) -> AgentBenchmark:
        """Run benchmark suite for an agent."""
        benchmark = AgentBenchmark(agent_name=agent_name, version=version)

        for test_case in test_cases:
            result = self._run_single_test(test_case, runner_func)
            benchmark.results.append(result)

        benchmark.calculate_overall_score()
        self.registry.register_benchmark(benchmark)

        return benchmark

    def _run_single_test(
        self,
        test_case: dict[str, Any],
        runner_func: callable,
    ) -> BenchmarkResult:
        """Run a single test case."""
        name = test_case["name"]
        input_data = test_case["input"]
        expected_output = test_case.get("expected_output")
        expected_duration_ms = test_case.get("max_duration_ms", 5000)

        start_time = time.time()
        error = None
        passed = False
        metrics = {}

        try:
            result = runner_func(input_data)
            duration_ms = int((time.time() - start_time) * 1000)

            if expected_output is not None:
                passed = self._check_result(result, expected_output)
            else:
                passed = True

            if not passed:
                score = 0.0
            else:
                duration_score = max(0, 1 - (duration_ms / expected_duration_ms))
                score = 0.8 + (duration_score * 0.2)

            metrics = {
                "result_size": len(str(result)),
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error = str(e)
            score = 0.0
            passed = False

        return BenchmarkResult(
            name=name,
            score=score,
            duration_ms=duration_ms,
            passed=passed,
            metrics=metrics,
            error=error,
        )

    def _check_result(self, actual: Any, expected: Any) -> bool:
        """Check if actual result matches expected."""
        if isinstance(expected, dict) and isinstance(actual, dict):
            return all(
                key in actual and self._check_result(actual[key], value)
                for key, value in expected.items()
            )
        return actual == expected


def run_quality_benchmarks(
    agent_name: str,
    version: str,
    test_cases: list[dict[str, Any]],
    runner_func: callable,
    storage_path: str | None = None,
) -> AgentBenchmark:
    """Run quality benchmarks for an agent.

    Args:
        agent_name: Name of the agent.
        version: Version of the agent.
        test_cases: List of test cases with input and expected_output.
        runner_func: Function to run with input_data.
        storage_path: Optional path to store benchmark results.

    Returns:
        AgentBenchmark with results.
    """
    registry = BenchmarkRegistry(storage_path=storage_path)
    runner = BenchmarkRunner(registry)
    return runner.run_benchmark(
        agent_name=agent_name,
        version=version,
        test_cases=test_cases,
        runner_func=runner_func,
    )


def get_agent_quality_report(
    agent_name: str,
    version: str,
    storage_path: str | None = None,
) -> dict[str, Any]:
    """Get quality report for an agent.

    Args:
        agent_name: Name of the agent.
        version: Version of the agent.
        storage_path: Optional path to load benchmark results from.

    Returns:
        Dict with agent quality report or error if not found.
    """
    registry = BenchmarkRegistry(storage_path=storage_path)
    benchmark = registry.get_latest_benchmark(agent_name, version)

    if not benchmark:
        return {"error": f"No benchmark found for {agent_name} version {version}"}

    passed_tests = sum(1 for r in benchmark.results if r.passed)
    total_tests = len(benchmark.results)

    return {
        "agent_name": agent_name,
        "version": version,
        "overall_score": benchmark.overall_score,
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "pass_rate": passed_tests / total_tests if total_tests > 0 else 0.0,
        "run_at": benchmark.run_at,
    }
