from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rag.embeddings import EmbeddingsProvider, cosine_similarity, resolve_embeddings_provider
from rag.indexer import tokenize_text


class ContextRetriever:
    def __init__(
        self,
        *,
        index_path: str = ".hordeforge_data/rag/docs_index.json",
        embeddings_provider: EmbeddingsProvider | None = None,
        embeddings_provider_name: str | None = "hash",
        embedding_dimension: int = 64,
    ) -> None:
        self.index_path = Path(index_path)
        self.embeddings_provider = resolve_embeddings_provider(
            provider=embeddings_provider,
            provider_name=embeddings_provider_name,
            dimension=embedding_dimension,
        )

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"documents": {}}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"documents": {}}
        if not isinstance(payload, dict):
            return {"documents": {}}
        documents = payload.get("documents", {})
        if not isinstance(documents, dict):
            documents = {}
        return {"documents": documents}

    def _score_entry(
        self,
        entry: dict[str, Any],
        query: str,
        query_tokens: set[str],
        query_embedding: list[float] | None,
    ) -> float:
        content = str(entry.get("content", ""))
        section_title = str(entry.get("section_title", ""))
        entry_tokens = (
            set(entry.get("tokens", [])) if isinstance(entry.get("tokens"), list) else set()
        )

        overlap = len(query_tokens.intersection(entry_tokens))
        content_lower = content.lower()
        query_lower = query.lower()
        phrase_bonus = 2.0 if query_lower and query_lower in content_lower else 0.0
        title_bonus = 1.0 if any(token in section_title.lower() for token in query_tokens) else 0.0
        lexical_score = (
            float(overlap) + phrase_bonus + title_bonus + (overlap / max(1, len(query_tokens)))
        )

        embedding_score = 0.0
        if self.embeddings_provider is not None and query_embedding:
            entry_embedding = self.embeddings_provider.embed_text(content)
            similarity = cosine_similarity(query_embedding, entry_embedding)
            if similarity > 0:
                embedding_score = similarity * 2.0

        if lexical_score <= 0 and embedding_score <= 0:
            return 0.0
        return lexical_score + embedding_score

    @staticmethod
    def _build_snippet(content: str, *, max_chars: int) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3].rstrip() + "..."

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 3,
        max_context_chars: int = 1500,
    ) -> dict[str, Any]:
        normalized_query = str(query).strip()
        normalized_top_k = max(1, int(top_k))
        normalized_max_chars = max(80, int(max_context_chars))
        if not normalized_query:
            return {
                "query": "",
                "top_k": normalized_top_k,
                "max_context_chars": normalized_max_chars,
                "items": [],
                "sources": [],
                "context": "",
                "context_size_chars": 0,
                "total_candidates": 0,
                "embedding_provider": (
                    self.embeddings_provider.name
                    if self.embeddings_provider is not None
                    else "none"
                ),
            }

        query_tokens = set(tokenize_text(normalized_query))
        query_embedding = (
            self.embeddings_provider.embed_text(normalized_query)
            if self.embeddings_provider is not None
            else None
        )
        index_payload = self._load_index()
        documents = index_payload["documents"]
        entries: list[dict[str, Any]] = []
        for document in documents.values():
            if not isinstance(document, dict):
                continue
            raw_entries = document.get("entries", [])
            if isinstance(raw_entries, list):
                entries.extend(item for item in raw_entries if isinstance(item, dict))

        ranked: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            score = self._score_entry(entry, normalized_query, query_tokens, query_embedding)
            if score <= 0:
                continue
            ranked.append((score, entry))

        ranked.sort(
            key=lambda item: (
                -item[0],
                str(item[1].get("source_path", "")),
                str(item[1].get("section_title", "")),
            )
        )

        selected_items: list[dict[str, Any]] = []
        source_refs: list[str] = []
        context_lines: list[str] = []
        context_size = 0
        for score, entry in ranked:
            source_path = str(entry.get("source_path", "")).strip()
            section_anchor = str(entry.get("section_anchor", "")).strip()
            section_title = str(entry.get("section_title", "")).strip()
            content = str(entry.get("content", ""))
            source_ref = (
                f"{source_path}#{section_anchor}" if source_path and section_anchor else source_path
            )
            snippet = self._build_snippet(content, max_chars=220)
            line = f"[{source_ref}] {snippet}" if source_ref else snippet
            projected_size = context_size + (1 if context_lines else 0) + len(line)
            if projected_size > normalized_max_chars:
                continue

            item_payload = {
                "score": round(score, 3),
                "source_path": source_path,
                "section_title": section_title,
                "section_anchor": section_anchor,
                "source_ref": source_ref,
                "snippet": snippet,
            }
            selected_items.append(item_payload)
            context_lines.append(line)
            context_size = projected_size
            if source_ref and source_ref not in source_refs:
                source_refs.append(source_ref)
            if len(selected_items) >= normalized_top_k:
                break

        context = "\n".join(context_lines)
        return {
            "query": normalized_query,
            "top_k": normalized_top_k,
            "max_context_chars": normalized_max_chars,
            "items": selected_items,
            "sources": source_refs,
            "context": context,
            "context_size_chars": len(context),
            "total_candidates": len(ranked),
            "embedding_provider": (
                self.embeddings_provider.name if self.embeddings_provider is not None else "none"
            ),
        }
