from __future__ import annotations

import shutil
from pathlib import Path

from agents.code_generator import CodeGenerator
from agents.specification_writer import SpecificationWriter
from rag import ContextRetriever, DocumentationIndexer, MockEmbeddingsProvider


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _build_index(base_dir: Path) -> Path:
    docs_dir = base_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "runtime.md").write_text(
        """
# Runtime Guide

## Reliability
Use deterministic execution and explicit retries.

## Testing
Validate changes with unit and integration tests.
""".strip(),
        encoding="utf-8",
    )
    (docs_dir / "security.md").write_text(
        """
# Security Guide

## Secrets
Never persist plaintext tokens in storage.
""".strip(),
        encoding="utf-8",
    )
    index_path = base_dir / "docs_index.json"
    DocumentationIndexer(source_dir=str(docs_dir), index_path=str(index_path)).index_markdown()
    return index_path


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    raise AssertionError(f"Artifact not found: {artifact_type}")


def test_retriever_returns_top_k_with_sources_and_context_limit():
    base_dir = Path("tests/unit/_tmp_rag_retrieve")
    _reset_dir(base_dir)

    try:
        index_path = _build_index(base_dir)
        retriever = ContextRetriever(index_path=str(index_path))
        result = retriever.retrieve(
            "deterministic retries and testing",
            top_k=2,
            max_context_chars=180,
        )
        assert len(result["items"]) <= 2
        assert result["items"]
        assert result["sources"]
        assert result["context_size_chars"] <= 180
        assert result["total_candidates"] >= len(result["items"])
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_retriever_returns_empty_payload_for_blank_query():
    retriever = ContextRetriever(index_path="tests/unit/_tmp_missing_index.json")
    result = retriever.retrieve("", top_k=3, max_context_chars=200)
    assert result["items"] == []
    assert result["sources"] == []
    assert result["context"] == ""


def test_retriever_supports_switchable_embedding_providers():
    base_dir = Path("tests/unit/_tmp_rag_retrieve_embeddings")
    _reset_dir(base_dir)
    try:
        index_path = _build_index(base_dir)
        hash_retriever = ContextRetriever(
            index_path=str(index_path),
            embeddings_provider_name="hash",
            embedding_dimension=32,
        )
        mock_retriever = ContextRetriever(
            index_path=str(index_path),
            embeddings_provider=MockEmbeddingsProvider(dimension=16),
        )
        hash_result = hash_retriever.retrieve("deterministic retries", top_k=2)
        mock_result = mock_retriever.retrieve("deterministic retries", top_k=2)

        assert hash_result["embedding_provider"] == "hash"
        assert mock_result["embedding_provider"] == "mock"
        assert hash_result["items"]
        assert mock_result["items"]
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_planning_and_coding_agents_consume_rag_context():
    rag_context = {
        "query": "security tokens",
        "sources": ["docs/security.md#secrets"],
        "items": [
            {
                "source_ref": "docs/security.md#secrets",
                "snippet": "Never persist plaintext tokens in storage.",
                "score": 4.0,
            }
        ],
        "context": "[docs/security.md#secrets] Never persist plaintext tokens in storage.",
    }

    spec_agent = SpecificationWriter()
    spec_result = spec_agent.run(
        {
            "dod_extractor": _step_result(
                "SUCCESS",
                "dod",
                {
                    "schema_version": "1.0",
                    "acceptance_criteria": ["Add endpoint", "Add tests"],
                    "bdd_scenarios": [],
                },
            ),
            "rag_retriever": _step_result("SUCCESS", "rag_context", rag_context),
        }
    )
    spec = _artifact_content(spec_result, "spec")
    notes = spec.get("notes", [])
    # Проверяем, что в notes есть ссылки на RAG-источники
    assert any("security.md" in str(item) or "rag" in str(item).lower() for item in notes)
    assert any("docs/security.md#secrets" in str(item) for item in spec.get("requirements", []))

    code_agent = CodeGenerator()
    code_result = code_agent.run(
        {
            "task_decomposer": _step_result(
                "SUCCESS",
                "subtasks",
                {"items": [{"id": "ST-01", "title": "Implement endpoint"}]},
            ),
            "test_generator": _step_result(
                "SUCCESS",
                "tests",
                {"schema_version": "1.0", "test_cases": [{"name": "test_endpoint"}]},
            ),
            "rag_retriever": _step_result("SUCCESS", "rag_context", rag_context),
        }
    )
    patch = _artifact_content(code_result, "code_patch")
    # Проверяем, что в решениях есть упоминания RAG-источников
    assert any(
        "security.md" in str(item) or "rag" in str(item).lower()
        for item in patch.get("decisions", [])
    )
