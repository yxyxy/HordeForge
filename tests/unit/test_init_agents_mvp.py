from pathlib import Path

from agents.architecture_evaluator import ArchitectureEvaluator
from agents.memory_agent import MemoryAgent
from agents.pipeline_initializer import PipelineInitializer
from agents.rag_initializer import RagInitializer
from agents.repo_connector import RepoConnector
from agents.test_analyzer import TestAnalyzer


def _artifact_content(result: dict, artifact_type: str) -> dict:
    artifacts = result.get("artifacts", [])
    for artifact in artifacts:
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    raise AssertionError(f"Artifact not found: {artifact_type}")


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


import pytest


@pytest.mark.asyncio
async def test_repo_connector_reads_repo_context_and_returns_metadata():
    agent = RepoConnector()
    result = await agent.run(
        {
            "repo_url": "https://github.com/acme/hordeforge.git",
            "github_token": "secret-token",
        }
    )

    assert result["status"] == "SUCCESS"
    metadata = _artifact_content(result, "repository_data")
    assert metadata["repo_url"] == "https://github.com/acme/hordeforge.git"
    assert metadata["owner"] == "acme"
    assert metadata["repo_name"] == "hordeforge"
    assert metadata["has_auth"] is True
    assert metadata["connection_mode"] == "live"
    assert "secret-token" not in str(result)


@pytest.mark.asyncio
async def test_repo_connector_supports_mock_mode():
    agent = RepoConnector()
    result = await agent.run(
        {
            "repo_url": "https://github.com/acme/hordeforge.git",
            "token": "abc",
            "mock_mode": True,
        }
    )

    metadata = _artifact_content(result, "repository_data")
    assert metadata["mock_mode"] is True
    assert metadata["connection_mode"] == "mock"


def test_rag_initializer_builds_minimal_docs_index():
    docs_dir = Path("tests/unit/_tmp_docs_rag_index")
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "a.md").write_text("# A", encoding="utf-8")
    (docs_dir / "b.md").write_text("# B", encoding="utf-8")

    try:
        agent = RagInitializer()
        result = agent.run({"docs_dir": str(docs_dir)})
    finally:
        for file_path in docs_dir.glob("*"):
            if file_path.is_file():
                file_path.unlink()
        docs_dir.rmdir()

    assert result["status"] == "SUCCESS"
    rag_index = _artifact_content(result, "rag_index")
    assert rag_index["documents_count"] == 2
    assert rag_index["documents"][0]["path"].endswith("a.md")
    assert rag_index["documents"][1]["path"].endswith("b.md")


def test_memory_agent_returns_downstream_ready_memory_state():
    agent = MemoryAgent()
    context = {
        "repo_connector": _step_result(
            "SUCCESS",
            "repository_metadata",
            {"repo_name": "hordeforge", "owner": "acme"},
        ),
        "rag_initializer": _step_result(
            "SUCCESS",
            "rag_index",
            {"documents_count": 3, "documents": [{"path": "docs/1.md"}]},
        ),
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    memory_state = _artifact_content(result, "memory_state")
    assert memory_state["repository"]["repo_name"] == "hordeforge"
    assert memory_state["knowledge"]["documents_count"] == 3
    assert isinstance(memory_state["events"], list)


def test_architecture_evaluator_returns_report_and_partial_when_context_missing():
    agent = ArchitectureEvaluator()
    result = agent.run({})

    assert result["status"] == "PARTIAL_SUCCESS"
    report = _artifact_content(result, "architecture_report")
    assert "findings" in report
    assert "risks" in report


def test_test_analyzer_handles_repo_without_tests_gracefully():
    agent = TestAnalyzer()
    result = agent.run({"test_files": []})

    assert result["status"] == "PARTIAL_SUCCESS"
    report = _artifact_content(result, "test_coverage_report")
    assert report["total_tests"] == 0
    assert report["fallback_reason"]


def test_pipeline_initializer_summarizes_init_step_results():
    agent = PipelineInitializer()
    context = {
        "repo_connector": _step_result(
            "SUCCESS", "repository_metadata", {"repo_name": "hordeforge"}
        ),
        "rag_initializer": _step_result("SUCCESS", "rag_index", {"documents_count": 2}),
        "memory_agent": _step_result("SUCCESS", "memory_state", {"events": []}),
        "architecture_evaluator": _step_result(
            "PARTIAL_SUCCESS",
            "architecture_report",
            {"risks": ["missing docs"]},
        ),
        "test_analyzer": _step_result(
            "PARTIAL_SUCCESS",
            "test_coverage_report",
            {"total_tests": 0},
        ),
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    pipeline_status = _artifact_content(result, "pipeline_status")
    assert pipeline_status["init_ready"] is True
    assert pipeline_status["steps"]["repo_connector"] == "SUCCESS"
    assert pipeline_status["steps"]["architecture_evaluator"] == "PARTIAL_SUCCESS"
