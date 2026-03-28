from __future__ import annotations

import shutil
from pathlib import Path

from rag import ContextRetriever, DocumentationIndexer
from rag.sources import MockDocumentSource


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def test_rag_package_imports_and_runs_with_mock_source():
    base_dir = Path("tests/unit/_tmp_rag_import")
    docs_dir = base_dir / "docs"
    index_path = base_dir / "docs_index.json"
    _reset_dir(base_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    try:
        source = MockDocumentSource()
        materialized = source.materialize(target_dir=str(docs_dir))
        assert len(materialized) >= 2

        indexer = DocumentationIndexer(source_dir=str(docs_dir), index_path=str(index_path))
        summary = indexer.index_markdown()
        assert summary["documents_indexed"] >= 2
        assert index_path.exists()

        retriever = ContextRetriever(index_path=str(index_path))
        result = retriever.retrieve("testing strategy", top_k=2, max_context_chars=400)
        assert result["items"]
        assert result["context_size_chars"] <= 400
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_indexer_stores_document_metadata_and_sections():
    base_dir = Path("tests/unit/_tmp_rag_metadata")
    docs_dir = base_dir / "docs"
    index_path = base_dir / "docs_index.json"
    _reset_dir(base_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "architecture.md").write_text(
        """
# Architecture Overview
System components and boundaries.

## Runtime
Runtime must be deterministic and observable.

## Security
Secrets should be redacted from persisted payloads.
""".strip(),
        encoding="utf-8",
    )

    try:
        indexer = DocumentationIndexer(source_dir=str(docs_dir), index_path=str(index_path))
        indexer.index_markdown()
        payload = indexer.load_index()
        documents = payload.get("documents", {})
        assert "architecture.md" in documents
        doc = documents["architecture.md"]
        assert doc["title"] == "Architecture Overview"
        assert doc["section_count"] >= 3
        assert doc["word_count"] > 0
        section_titles = [item.get("section_title") for item in doc.get("entries", [])]
        assert "Runtime" in section_titles
        assert "Security" in section_titles
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_indexer_incremental_reindex_is_repeatable():
    base_dir = Path("tests/unit/_tmp_rag_incremental")
    docs_dir = base_dir / "docs"
    index_path = base_dir / "docs_index.json"
    _reset_dir(base_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_path = docs_dir / "guide.md"
    doc_path.write_text("# Guide\n\nStable baseline content.\n", encoding="utf-8")

    try:
        indexer = DocumentationIndexer(source_dir=str(docs_dir), index_path=str(index_path))
        first = indexer.index_markdown(incremental=True)
        second = indexer.index_markdown(incremental=True)
        assert first["documents_indexed"] == 1
        assert second["updated_documents"] == []
        assert second["skipped_documents"] == ["guide.md"]

        doc_path.write_text(
            "# Guide\n\nStable baseline content.\n\nUpdated paragraph.\n", encoding="utf-8"
        )
        third = indexer.index_markdown(incremental=True)
        assert third["updated_documents"] == ["guide.md"]
        assert third["skipped_documents"] == []
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
