from __future__ import annotations

import pytest

from observability.benchmarking import (
    build_baseline_vs_optimized_report,
    build_latency_benchmark,
    build_throughput_benchmark,
    default_burst_scenarios,
    evaluate_burst_result,
)


def test_build_latency_benchmark_returns_pipeline_and_step_percentiles():
    run_results = [
        {
            "summary": {
                "step_durations_seconds": {"a": 0.10, "b": 0.20},
            }
        },
        {
            "summary": {
                "step_durations_seconds": {"a": 0.20, "b": 0.40},
            }
        },
    ]

    metrics = build_latency_benchmark(run_results)

    assert metrics["runs_observed"] == 2
    assert metrics["pipeline_latency_seconds"]["p50"] == pytest.approx(0.30)
    assert metrics["pipeline_latency_seconds"]["p95"] == pytest.approx(0.60)
    assert metrics["steps"]["a"]["p95"] == pytest.approx(0.20)
    assert metrics["steps"]["b"]["avg"] == pytest.approx(0.30)


def test_build_throughput_benchmark_returns_rps_and_per_worker_rate():
    throughput = build_throughput_benchmark(
        total_runs=120, duration_seconds=10.0, parallel_workers=6
    )

    assert throughput["runs_per_second"] == pytest.approx(12.0)
    assert throughput["runs_per_second_per_worker"] == pytest.approx(2.0)


def test_build_baseline_vs_optimized_report_calculates_delta_and_improvement():
    baseline = {
        "latency": {"pipeline_latency_seconds": {"p95": 6.0}},
        "throughput": {"runs_per_second": 20.0},
    }
    optimized = {
        "latency": {"pipeline_latency_seconds": {"p95": 4.5}},
        "throughput": {"runs_per_second": 28.0},
    }

    report = build_baseline_vs_optimized_report(baseline=baseline, optimized=optimized)

    assert report["latency_p95_delta_seconds"] == pytest.approx(1.5)
    assert report["latency_p95_improvement_percent"] == pytest.approx(25.0)
    assert report["throughput_delta_rps"] == pytest.approx(8.0)
    assert report["throughput_improvement_percent"] == pytest.approx(40.0)


def test_default_burst_scenarios_include_100_250_500_profiles():
    sizes = [item.burst_size for item in default_burst_scenarios()]

    assert sizes == [100, 250, 500]


def test_evaluate_burst_result_returns_saturation_and_budget_flags():
    green = evaluate_burst_result(burst_size=100, started_count=100, p95_latency_seconds=4.5)
    yellow = evaluate_burst_result(burst_size=250, started_count=243, p95_latency_seconds=8.1)
    red = evaluate_burst_result(burst_size=500, started_count=430, p95_latency_seconds=20.0)

    assert green["saturation"] == "green"
    assert green["within_error_budget"] is True
    assert green["within_latency_budget"] is True
    assert yellow["saturation"] == "yellow"
    assert red["saturation"] == "red"
    assert red["within_error_budget"] is False
    assert red["within_latency_budget"] is False
