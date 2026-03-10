from __future__ import annotations

from observability.metrics import RuntimeMetrics


def test_runtime_metrics_tracks_run_counters():
    metrics = RuntimeMetrics()

    metrics.mark_run_started()
    metrics.mark_run_started()
    metrics.observe_run_result({"status": "SUCCESS", "summary": {}})
    metrics.observe_run_result({"status": "BLOCKED", "summary": {}})
    metrics.observe_run_result({"status": "FAILED", "summary": {}})

    rendered = metrics.render_prometheus()
    assert "hordeforge_runs_started_total 2" in rendered
    assert "hordeforge_runs_succeeded_total 1" in rendered
    assert "hordeforge_runs_blocked_total 1" in rendered
    assert "hordeforge_runs_failed_total 1" in rendered


def test_runtime_metrics_tracks_step_duration_and_retries():
    metrics = RuntimeMetrics()

    metrics.observe_run_result(
        {
            "status": "SUCCESS",
            "summary": {
                "total_retries": 3,
                "step_durations_seconds": {"a": 1.0, "b": 2.0},
            },
        }
    )

    rendered = metrics.render_prometheus()
    assert "hordeforge_step_duration_seconds_sum 3.0" in rendered
    assert "hordeforge_step_duration_seconds_count 2" in rendered
    assert "hordeforge_step_duration_seconds_avg 1.5" in rendered
    assert "hordeforge_step_retries_total 3" in rendered
