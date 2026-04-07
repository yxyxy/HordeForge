from __future__ import annotations

from scheduler.jobs.ci_monitor import CiMonitorJob
from scheduler.jobs.dependency_checker import DependencyCheckerJob
from scheduler.jobs.issue_scanner import IssueScannerJob


def test_issue_scanner_triggers_all_agent_stages_and_prevents_duplicates():
    job = IssueScannerJob()
    payload = {
        "labels": ["agent:opened", "agent:planning", "agent:ready", "agent:fixed"],
        "issues": [
            {"id": 1, "labels": [{"name": "agent:opened"}]},
            {"id": 4, "labels": [{"name": "agent:planning"}]},
            {"id": 3, "labels": [{"name": "agent:ready"}]},
            {"id": 5, "labels": [{"name": "agent:fixed"}]},
            {"id": 2, "labels": [{"name": "bug"}]},
        ],
    }

    first = job.run(payload)
    second = job.run(payload)

    assert first["trigger_count"] == 4
    assert first["triggers"][0]["pipeline_name"] == "issue_scanner_pipeline"
    assert second["trigger_count"] == 0


def test_ci_monitor_triggers_failed_runs_once():
    job = CiMonitorJob()
    payload = {
        "repository": {"full_name": "acme/hordeforge"},
        "workflow_runs": [
            {"id": 11, "status": "completed", "conclusion": "failure"},
            {"id": 12, "status": "completed", "conclusion": "success"},
        ],
    }

    first = job.run(payload)
    second = job.run(payload)

    assert first["trigger_count"] == 1
    assert first["triggers"][0]["pipeline_name"] == "ci_scanner_pipeline"
    assert second["trigger_count"] == 0


def test_ci_monitor_logs_processed_run_ids(caplog):
    job = CiMonitorJob()
    payload = {
        "repository": {"full_name": "acme/hordeforge"},
        "workflow_runs": [{"id": 22, "status": "completed", "conclusion": "failure"}],
    }

    with caplog.at_level("INFO", logger="hordeforge.scheduler.jobs.ci_monitor"):
        result = job.run(payload)

    assert result["processed_run_ids"] == [22]
    assert any("ci_monitor_processed_runs" in record.message for record in caplog.records)


def test_dependency_checker_applies_critical_filter_and_outputs_triggers():
    job = DependencyCheckerJob()
    payload = {
        "critical_only": True,
        "dependencies": [
            {
                "name": "openssl",
                "current_version": "1.0.0",
                "latest_version": "1.2.0",
                "severity": "critical",
            },
            {
                "name": "pytest",
                "current_version": "8.0.0",
                "latest_version": "8.1.0",
                "severity": "low",
            },
        ],
    }

    result = job.run(payload)

    assert result["findings_count"] == 1
    assert result["findings"][0]["name"] == "openssl"
    assert result["triggers"][0]["pipeline_name"] == "dependency_check_pipeline"
