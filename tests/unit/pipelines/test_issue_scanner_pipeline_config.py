from __future__ import annotations

from pathlib import Path

import yaml


def _load_pipeline() -> dict:
    path = Path("pipelines/issue_scanner_pipeline.yaml")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_issue_scanner_pipeline_dispatches_ci_incidents_to_ci_fix_pipeline() -> None:
    pipeline = _load_pipeline()

    issue_dispatch_step = next(
        step for step in pipeline["steps"] if step["name"] == "issue_dispatch"
    )
    step_input = issue_dispatch_step["input"]

    assert step_input["target_pipeline"] == "feature_pipeline"
    assert step_input["ci_incident_pipeline"] == "ci_fix_pipeline"


def test_issue_scanner_pipeline_uses_issue_pipeline_dispatcher() -> None:
    pipeline = _load_pipeline()

    issue_dispatch_step = next(
        step for step in pipeline["steps"] if step["name"] == "issue_dispatch"
    )

    assert issue_dispatch_step["agent"] == "issue_pipeline_dispatcher"
    assert issue_dispatch_step["on_failure"] == "continue"
