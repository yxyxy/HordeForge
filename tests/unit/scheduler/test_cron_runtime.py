from __future__ import annotations

from typing import Any

from scheduler.cron_runtime import build_default_cron_dispatcher


def test_default_cron_runtime_registers_enabled_jobs_only():
    dispatcher = build_default_cron_dispatcher(
        lambda _pipeline, _inputs, _source, _idempotency: {"status": "started", "run_id": "noop"}
    )

    assert "issue_scanner" in dispatcher.jobs
    assert "ci_monitor" in dispatcher.jobs
    assert "dependency_checker" not in dispatcher.jobs


def test_issue_scanner_job_publishes_issue_scanner_trigger_via_runtime_wrapper():
    published_calls: list[dict[str, Any]] = []

    def _trigger_pipeline(
        pipeline_name: str,
        inputs: dict[str, Any],
        source: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        published_calls.append(
            {
                "pipeline_name": pipeline_name,
                "inputs": inputs,
                "source": source,
                "idempotency_key": idempotency_key,
            }
        )
        return {"status": "started", "run_id": "run-scan-1"}

    dispatcher = build_default_cron_dispatcher(_trigger_pipeline)
    result = dispatcher.trigger_job(
        "issue_scanner",
        payload={"issues": [{"id": 101, "labels": [{"name": "agent:opened"}]}]},
    )

    assert result["status"] == "SUCCESS"
    assert result["result"]["trigger_count"] == 1
    assert result["result"]["published_count"] == 1
    assert published_calls[0]["pipeline_name"] == "issue_scanner_pipeline"
    assert published_calls[0]["source"] == "cron:issue_scanner"
    assert published_calls[0]["idempotency_key"] == "issue_scanner:101"


def test_ci_monitor_job_publishes_ci_fix_trigger_via_runtime_wrapper():
    published_calls: list[dict[str, Any]] = []

    def _trigger_pipeline(
        pipeline_name: str,
        inputs: dict[str, Any],
        source: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        published_calls.append(
            {
                "pipeline_name": pipeline_name,
                "inputs": inputs,
                "source": source,
                "idempotency_key": idempotency_key,
            }
        )
        return {"status": "started", "run_id": "run-ci-1"}

    dispatcher = build_default_cron_dispatcher(_trigger_pipeline)
    result = dispatcher.trigger_job(
        "ci_monitor",
        payload={
            "repository": {"full_name": "acme/hordeforge"},
            "workflow_runs": [{"id": 77, "status": "completed", "conclusion": "failure"}],
        },
    )

    assert result["status"] == "SUCCESS"
    assert result["result"]["trigger_count"] == 1
    assert result["result"]["processed_run_ids"] == [77]
    assert result["result"]["published_count"] == 1
    assert published_calls[0]["pipeline_name"] == "ci_fix_pipeline"
    assert published_calls[0]["source"] == "cron:ci_monitor"
    assert published_calls[0]["idempotency_key"] == "ci_monitor:77"
