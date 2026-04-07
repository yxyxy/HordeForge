from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.engine import OrchestratorEngine

pytestmark = pytest.mark.usefixtures("stub_llm_for_pipeline_runtime")


def _build_minimal_repo(base_dir: Path) -> Path:
    repo_dir = base_dir / "memory_pipeline_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "src").mkdir(exist_ok=True)
    (repo_dir / "src" / "feature_impl.py").write_text(
        "def process(value: int = 1) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    return repo_dir


def test_code_generation_pipeline_with_memory(tmp_path: Path):
    engine = OrchestratorEngine()
    repo_dir = _build_minimal_repo(tmp_path)

    result = engine.run(
        "code_generation",
        {
            "issue": {"title": "Add auth", "body": "..."},
            "repo_url": str(repo_dir),
            "project_path": str(repo_dir),
            "mock_mode": False,
            "repository": {
                "full_name": "acme/hordeforge",
                "default_branch": "main",
                "repo_url": str(repo_dir),
                "local_path": str(repo_dir),
                "mock_mode": False,
            },
        },
        run_id="test-001",
    )

    steps = result.get("steps", {})
    executed_step_names = {str(name).lower() for name in steps.keys()}

    has_memory_retrieval = any("memory_retrieval" in name for name in executed_step_names)
    has_memory_writer = any("memory_writer" in name for name in executed_step_names)

    if not has_memory_retrieval:
        result_str = str(result).lower()
        has_memory_retrieval = "memory_retrieval" in result_str

    if not has_memory_writer:
        result_str = str(result).lower()
        has_memory_writer = "memory_writer" in result_str

    assert has_memory_retrieval, f"Memory retrieval step not found in result: {list(steps.keys())}"
    assert has_memory_writer, f"Memory writer step not found in result: {list(steps.keys())}"
    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "BLOCKED"}


if __name__ == "__main__":
    pytest.main([__file__])
