from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def tokenize_text(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+", str(text).lower())
    # Preserve stable order while removing duplicates.
    return list(dict.fromkeys(tokens))


class DocumentationIndexer:
    def __init__(
        self,
        *,
        source_dir: str = "docs",
        index_path: str = ".hordeforge_data/rag/docs_index.json",
    ) -> None:
        self.source_dir = Path(source_dir)
        self.index_path = Path(index_path)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _checksum(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _slugify(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return cleaned or "section"

    def _default_index_payload(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "source_dir": str(self.source_dir).replace("\\", "/"),
            "updated_at": None,
            "documents": {},
        }

    def load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._default_index_payload()
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default_index_payload()
        if not isinstance(payload, dict):
            return self._default_index_payload()
        documents = payload.get("documents")
        if not isinstance(documents, dict):
            payload["documents"] = {}
        return payload

    def _write_index(self, payload: dict[str, Any]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.index_path.with_suffix(f"{self.index_path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.index_path)

    def _parse_sections(
        self, content: str, fallback_title: str
    ) -> tuple[str, list[dict[str, str]]]:
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
        doc_title = fallback_title
        sections: list[dict[str, str]] = []
        current_title = "Introduction"
        current_lines: list[str] = []
        used_anchors: dict[str, int] = {}

        def flush_section() -> None:
            section_content = "\n".join(current_lines).strip()
            if not section_content:
                current_lines.clear()
                return
            anchor_base = self._slugify(current_title)
            anchor_count = used_anchors.get(anchor_base, 0)
            used_anchors[anchor_base] = anchor_count + 1
            anchor = anchor_base if anchor_count == 0 else f"{anchor_base}-{anchor_count + 1}"
            sections.append(
                {
                    "title": current_title,
                    "anchor": anchor,
                    "content": section_content,
                }
            )
            current_lines.clear()

        for line in content.splitlines():
            heading_match = heading_pattern.match(line)
            if heading_match:
                flush_section()
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                if level == 1 and doc_title == fallback_title:
                    doc_title = heading_text or fallback_title
                current_title = heading_text or f"Section {len(sections) + 1}"
                continue
            current_lines.append(line)

        flush_section()
        if not sections and content.strip():
            sections.append(
                {
                    "title": doc_title,
                    "anchor": self._slugify(doc_title),
                    "content": content.strip(),
                }
            )
        return doc_title, sections

    def _build_document_record(
        self,
        *,
        relative_path: str,
        content: str,
        checksum: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        fallback_title = Path(relative_path).stem.replace("_", " ").replace("-", " ").title()
        title, sections = self._parse_sections(content, fallback_title=fallback_title)
        entries: list[dict[str, Any]] = []
        total_word_count = 0

        for section in sections:
            section_content = section["content"]
            tokens = tokenize_text(section_content)
            word_count = len(section_content.split())
            total_word_count += word_count
            entry = {
                "entry_id": f"{relative_path}#{section['anchor']}",
                "source_path": relative_path,
                "document_title": title,
                "section_title": section["title"],
                "section_anchor": section["anchor"],
                "content": section_content,
                "tokens": tokens,
                "token_count": len(tokens),
                "word_count": word_count,
            }
            entries.append(entry)

        document_record = {
            "path": relative_path,
            "title": title,
            "checksum": checksum,
            "indexed_at": self._utc_now_iso(),
            "section_count": len(entries),
            "word_count": total_word_count,
            "entries": entries,
        }
        return document_record, entries

    def _iter_markdown_paths(self) -> list[Path]:
        if not self.source_dir.exists():
            return []
        return sorted(path for path in self.source_dir.rglob("*.md") if path.is_file())

    def index_markdown(self, *, incremental: bool = True) -> dict[str, Any]:
        existing = self.load_index()
        existing_documents = existing.get("documents", {})
        if not isinstance(existing_documents, dict):
            existing_documents = {}

        updated_documents: list[str] = []
        skipped_documents: list[str] = []
        indexed_documents: dict[str, dict[str, Any]] = {}
        all_entries: list[dict[str, Any]] = []

        for path in self._iter_markdown_paths():
            relative_path = path.relative_to(self.source_dir).as_posix()
            content = path.read_text(encoding="utf-8")
            checksum = self._checksum(content)
            previous_document = existing_documents.get(relative_path)
            previous_checksum = (
                str(previous_document.get("checksum", "")).strip()
                if isinstance(previous_document, dict)
                else ""
            )

            if incremental and previous_checksum == checksum:
                indexed_documents[relative_path] = previous_document
                previous_entries = previous_document.get("entries", [])
                if isinstance(previous_entries, list):
                    all_entries.extend(item for item in previous_entries if isinstance(item, dict))
                skipped_documents.append(relative_path)
                continue

            document_record, entries = self._build_document_record(
                relative_path=relative_path,
                content=content,
                checksum=checksum,
            )
            indexed_documents[relative_path] = document_record
            all_entries.extend(entries)
            updated_documents.append(relative_path)

        removed_documents = sorted(set(existing_documents.keys()) - set(indexed_documents.keys()))
        payload = {
            "version": "1.0",
            "source_dir": str(self.source_dir).replace("\\", "/"),
            "updated_at": self._utc_now_iso(),
            "documents": indexed_documents,
        }
        self._write_index(payload)

        return {
            "index_path": str(self.index_path),
            "source_dir": str(self.source_dir),
            "incremental": incremental,
            "documents_indexed": len(indexed_documents),
            "entries_indexed": len(all_entries),
            "updated_documents": sorted(updated_documents),
            "skipped_documents": sorted(skipped_documents),
            "removed_documents": removed_documents,
        }
