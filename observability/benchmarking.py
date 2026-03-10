from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    normalized = sorted(max(0.0, float(item)) for item in values)
    rank = int(math.ceil((percentile / 100.0) * len(normalized))) - 1
    rank = max(0, min(rank, len(normalized) - 1))
    return normalized[rank]


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "avg": 0.0}
    normalized = [max(0.0, float(item)) for item in values]
    return {
        "min": min(normalized),
        "p50": _percentile(normalized, 50.0),
        "p95": _percentile(normalized, 95.0),
        "max": max(normalized),
        "avg": sum(normalized) / len(normalized),
    }


def build_latency_benchmark(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    per_step_samples: dict[str, list[float]] = {}
    pipeline_samples: list[float] = []
    observed_runs = 0

    for run_result in run_results:
        if not isinstance(run_result, dict):
            continue
        summary = run_result.get("summary")
        if not isinstance(summary, dict):
            continue
        step_durations = summary.get("step_durations_seconds")
        if not isinstance(step_durations, dict):
            continue
        observed_runs += 1
        pipeline_duration = 0.0
        for step_name, raw_value in step_durations.items():
            if not isinstance(step_name, str):
                continue
            if not isinstance(raw_value, (int, float)):
                continue
            value = max(0.0, float(raw_value))
            per_step_samples.setdefault(step_name, []).append(value)
            pipeline_duration += value
        pipeline_samples.append(pipeline_duration)

    step_metrics = {
        step_name: _summarize(samples) for step_name, samples in sorted(per_step_samples.items())
    }
    return {
        "runs_observed": observed_runs,
        "pipeline_latency_seconds": _summarize(pipeline_samples),
        "steps": step_metrics,
    }


def build_throughput_benchmark(
    *,
    total_runs: int,
    duration_seconds: float,
    parallel_workers: int,
) -> dict[str, Any]:
    normalized_runs = max(0, int(total_runs))
    normalized_workers = max(1, int(parallel_workers))
    normalized_duration = max(0.001, float(duration_seconds))
    runs_per_second = normalized_runs / normalized_duration
    return {
        "total_runs": normalized_runs,
        "duration_seconds": normalized_duration,
        "parallel_workers": normalized_workers,
        "runs_per_second": runs_per_second,
        "runs_per_second_per_worker": runs_per_second / normalized_workers,
    }


def build_baseline_vs_optimized_report(
    *,
    baseline: dict[str, Any],
    optimized: dict[str, Any],
) -> dict[str, Any]:
    baseline_latency = float(
        baseline.get("latency", {}).get("pipeline_latency_seconds", {}).get("p95", 0.0)
    )
    optimized_latency = float(
        optimized.get("latency", {}).get("pipeline_latency_seconds", {}).get("p95", 0.0)
    )
    baseline_throughput = float(baseline.get("throughput", {}).get("runs_per_second", 0.0))
    optimized_throughput = float(optimized.get("throughput", {}).get("runs_per_second", 0.0))

    latency_delta = baseline_latency - optimized_latency
    throughput_delta = optimized_throughput - baseline_throughput
    latency_improvement_pct = (
        (latency_delta / baseline_latency) * 100.0 if baseline_latency > 0 else 0.0
    )
    throughput_improvement_pct = (
        (throughput_delta / baseline_throughput) * 100.0 if baseline_throughput > 0 else 0.0
    )
    return {
        "latency_p95_baseline_seconds": baseline_latency,
        "latency_p95_optimized_seconds": optimized_latency,
        "latency_p95_delta_seconds": latency_delta,
        "latency_p95_improvement_percent": latency_improvement_pct,
        "throughput_baseline_rps": baseline_throughput,
        "throughput_optimized_rps": optimized_throughput,
        "throughput_delta_rps": throughput_delta,
        "throughput_improvement_percent": throughput_improvement_pct,
    }


@dataclass(frozen=True, slots=True)
class BurstScenario:
    burst_size: int
    max_error_rate: float
    max_p95_latency_seconds: float


def default_burst_scenarios() -> list[BurstScenario]:
    return [
        BurstScenario(burst_size=100, max_error_rate=0.01, max_p95_latency_seconds=5.0),
        BurstScenario(burst_size=250, max_error_rate=0.02, max_p95_latency_seconds=8.0),
        BurstScenario(burst_size=500, max_error_rate=0.05, max_p95_latency_seconds=12.0),
    ]


def evaluate_burst_result(
    *,
    burst_size: int,
    started_count: int,
    p95_latency_seconds: float,
    scenarios: list[BurstScenario] | None = None,
) -> dict[str, Any]:
    selected = None
    for scenario in scenarios or default_burst_scenarios():
        if scenario.burst_size == int(burst_size):
            selected = scenario
            break
    if selected is None:
        raise ValueError(f"Burst scenario is not configured: {burst_size}")

    normalized_burst = max(1, int(burst_size))
    normalized_started = max(0, min(normalized_burst, int(started_count)))
    error_count = normalized_burst - normalized_started
    error_rate = error_count / normalized_burst
    p95 = max(0.0, float(p95_latency_seconds))
    within_error_budget = error_rate <= selected.max_error_rate
    within_latency_budget = p95 <= selected.max_p95_latency_seconds

    if within_error_budget and within_latency_budget:
        saturation = "green"
    elif error_rate > (selected.max_error_rate * 2) or p95 > (
        selected.max_p95_latency_seconds * 1.5
    ):
        saturation = "red"
    else:
        saturation = "yellow"

    return {
        "burst_size": normalized_burst,
        "started_count": normalized_started,
        "error_count": error_count,
        "error_rate": error_rate,
        "p95_latency_seconds": p95,
        "error_budget_limit": selected.max_error_rate,
        "latency_budget_limit_seconds": selected.max_p95_latency_seconds,
        "within_error_budget": within_error_budget,
        "within_latency_budget": within_latency_budget,
        "saturation": saturation,
    }
