from __future__ import annotations

from pathlib import Path

from agents.context_utils import build_agent_result, get_artifact_from_context


class RagInitializer:
    name = "rag_initializer"
    description = "Builds a deterministic lightweight RAG index from local docs."

    @staticmethod
    def _collect_docs(docs_dir: Path) -> list[dict[str, object]]:
        if not docs_dir.exists() or not docs_dir.is_dir():
            return []

        files: list[Path] = []
        for suffix in ("*.md", "*.rst", "*.txt"):
            files.extend(docs_dir.rglob(suffix))
        files = sorted({file_path for file_path in files}, key=lambda value: value.as_posix())

        documents: list[dict[str, object]] = []
        for file_path in files:
            stat = file_path.stat()
            documents.append(
                {
                    "path": file_path.as_posix(),
                    "size_bytes": stat.st_size,
                }
            )
        return documents

    def run(self, context: dict) -> dict:
        docs_dir_raw = context.get("docs_dir", "docs")
        docs_dir = Path(str(docs_dir_raw))
        documents = self._collect_docs(docs_dir)
        repository_metadata = (
            get_artifact_from_context(
                context,
                "repository_metadata",
                preferred_steps=["repo_connector"],
            )
            or {}
        )

        rag_index = {
            "index_id": "rag_index_v1",
            "documents_count": len(documents),
            "documents": documents,
            "source_repo": repository_metadata.get("full_name", "unknown"),
            "deterministic": True,
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="rag_index",
            artifact_content=rag_index,
            reason="Lightweight deterministic docs index built for MVP runtime.",
            confidence=0.88,
            logs=[f"Indexed {len(documents)} documents from {docs_dir.as_posix()}."],
            next_actions=["memory_agent"],
        )
