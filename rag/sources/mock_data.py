from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class MockDocumentSource:
    def __init__(self, *, source_dir: str = "rag/sources/mock_docs") -> None:
        self.source_dir = Path(source_dir)

    @staticmethod
    def _extract_title(content: str, fallback: str) -> str:
        for line in content.splitlines():
            match = re.match(r"^#\s+(.+?)\s*$", line.strip())
            if match:
                return match.group(1).strip()
        return fallback

    def list_documents(self) -> list[dict[str, Any]]:
        if not self.source_dir.exists():
            return []
        documents: list[dict[str, Any]] = []
        for path in sorted(self.source_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            title = self._extract_title(content, fallback=path.stem.replace("_", " ").title())
            documents.append(
                {
                    "path": path.as_posix(),
                    "title": title,
                    "content": content,
                }
            )
        return documents

    def materialize(self, *, target_dir: str) -> list[str]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        written_paths: list[str] = []
        for document in self.list_documents():
            file_name = Path(str(document["path"])).name
            out_path = target / file_name
            out_path.write_text(str(document["content"]), encoding="utf-8")
            written_paths.append(out_path.as_posix())
        return written_paths
