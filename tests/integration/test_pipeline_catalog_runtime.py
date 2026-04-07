from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from orchestrator.engine import OrchestratorEngine

pytestmark = pytest.mark.usefixtures("stub_llm_for_pipeline_runtime")

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
        "ci_scanner_pipeline",
        {},
        {"ci_failure_analyzer", "ci_incident_handoff"},
        id="ci_scanner",
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
        "dependency_check_pipeline",
        {},
        {"architecture_evaluator", "test_analyzer"},
        id="dependency_check",
    ),
]


def _build_minimal_repo(base_dir: Path) -> Path:
    repo_dir = base_dir / "runtime_smoke_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "src").mkdir(exist_ok=True)
    (repo_dir / "tests").mkdir(exist_ok=True)
    (repo_dir / "src" / "feature_impl.py").write_text(
        "def process(value: int = 1) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo_dir / "tests" / "test_feature_impl.py").write_text(
        "from src.feature_impl import process\n\n\ndef test_process() -> None:\n    assert process(1) == 2\n",
        encoding="utf-8",
    )
    return repo_dir


@pytest.mark.parametrize("pipeline_name,input_overrides,expected_steps", PIPELINE_CASES)
def test_pipeline_catalog_runtime_smoke(
    pipeline_name: str,
    input_overrides: dict,
    expected_steps: set[str],
    tmp_path: Path,
):
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    repo_dir = _build_minimal_repo(tmp_path)

    inputs = deepcopy(COMMON_INPUTS)
    inputs.update(input_overrides)
    inputs["repo_url"] = str(repo_dir)
    inputs["project_path"] = str(repo_dir)
    inputs["mock_mode"] = False
    repository = inputs.get("repository")
    if not isinstance(repository, dict):
        repository = {}
        inputs["repository"] = repository
    repository["repo_url"] = str(repo_dir)
    repository["local_path"] = str(repo_dir)
    repository["mock_mode"] = False

    result = engine.run(
        pipeline_name,
        inputs,
        run_id=f"it-smoke-{pipeline_name}",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "BLOCKED"}
    executed_steps = set(result["steps"].keys())
    if result["status"] == "BLOCKED":
        assert expected_steps.intersection(executed_steps)
    else:
        assert expected_steps.issubset(executed_steps)
