from __future__ import annotations

from copy import deepcopy

import pytest

from orchestrator.engine import OrchestratorEngine

COMMON_INPUTS = {
    "mock_mode": True,
    "repo_url": "https://github.com/yxyxy/hordeforge.git",
    "github_token": "secret",
    "token": "secret",
    "repository": {"full_name": "acme/hordeforge", "default_branch": "main"},
    "issue": {
        "id": 101,
        "number": 101,
        "title": "Pipeline smoke issue",
        "body": "Implement endpoint and tests",
        "labels": [{"name": "agent:opened"}],
        "state": "open",
    },
    "ci_run": {
        "id": 501,
        "status": "completed",
        "conclusion": "failure",
        "failed_jobs": [{"name": "unit-tests", "reason": "assertion failure"}],
    },
    "original_issue": {"id": 7001, "title": "CI failure"},
    "dependency": {
        "name": "requests",
        "current_version": "2.25.0",
        "latest_version": "2.32.0",
        "severity": "high",
    },
}


PIPELINE_CASES = [
    pytest.param("init_pipeline", {}, {"repo_connector", "pipeline_initializer"}, id="init"),
    pytest.param("feature_pipeline", {}, {"code_generator", "pr_merge_agent"}, id="feature"),
    pytest.param(
        "ci_fix_pipeline",
        {},
        {"ci_failure_analyzer", "ci_incident_handoff"},
        id="ci_fix",
    ),
    pytest.param(
        "code_generation", {}, {"memory_retrieval", "memory_writer"}, id="code_generation"
    ),
    pytest.param(
        "issue_scanner_pipeline",
        {},
        {"repo_connector", "issue_classification", "issue_dispatch"},
        id="issue_scanner",
    ),
    pytest.param(
        "ci_monitoring_pipeline",
        {},
        {"ci_failure_analyzer", "issue_closer"},
        id="ci_monitoring",
    ),
    pytest.param(
        "dependency_check_pipeline",
        {},
        {"architecture_evaluator", "test_analyzer"},
        id="dependency_check",
    ),
]


@pytest.mark.parametrize("pipeline_name,input_overrides,expected_steps", PIPELINE_CASES)
def test_pipeline_catalog_runtime_smoke(
    pipeline_name: str,
    input_overrides: dict,
    expected_steps: set[str],
):
    engine = OrchestratorEngine(pipelines_dir="pipelines")

    inputs = deepcopy(COMMON_INPUTS)
    inputs.update(input_overrides)

    result = engine.run(
        pipeline_name,
        inputs,
        run_id=f"it-smoke-{pipeline_name}",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert expected_steps.issubset(set(result["steps"].keys()))
