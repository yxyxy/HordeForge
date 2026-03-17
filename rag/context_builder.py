from typing import Any

from rag.hybrid_retriever import HybridRetriever
from rag.memory_retriever import MemoryRetriever


class ContextBuilder:
    """
    Класс для построения контекста для агентов с учетом памяти и RAG репозитория
    """

    def __init__(self, memory_retriever: MemoryRetriever, rag_retriever: HybridRetriever):
        self.memory_retriever = memory_retriever
        self.rag_retriever = rag_retriever

    def build_agent_context(
        self,
        query: str,
        max_memory_entries: int = 5,
        max_rag_chunks: int = 10,
        max_tokens: int | None = 4000,
    ) -> str:
        """
        Строит контекст для агента, объединяя память и RAG репозитория

        Args:
            query: Запрос агента
            max_memory_entries: Максимальное количество записей из памяти
            max_rag_chunks: Максимальное количество чанков из RAG
            max_tokens: Максимальное количество токенов в итоговом контексте

        Returns:
            Сформированный контекст в виде строки
        """
        # Получаем релевантные записи из памяти
        memory_results = self.memory_retriever.search_memory(query, limit=max_memory_entries)

        # Получаем релевантные чанки из репозитория
        rag_results = self.rag_retriever.retrieve(query, limit=max_rag_chunks)

        # Формируем контекст
        context_parts = []

        # Добавляем секцию с предыдущими решениями
        if memory_results:
            memory_section = self._format_memory_section(memory_results)
            context_parts.append(memory_section)

        # Добавляем секцию с контекстом репозитория
        if rag_results:
            rag_section = self._format_rag_section(rag_results)
            context_parts.append(rag_section)

        # Объединяем все части контекста
        full_context = "\n\n".join(context_parts)

        # Если указан лимит токенов, ограничиваем размер контекста
        if max_tokens:
            full_context = self._limit_context_tokens(full_context, max_tokens)

        return full_context

    def _format_memory_section(self, memory_results: list[dict[str, Any]]) -> str:
        """
        Форматирует секцию с предыдущими решениями из памяти
        """
        section_parts = ["Previous solutions:"]

        for result in memory_results:
            entry_data = result.get("payload", {})
            entry_type = entry_data.get("type", "unknown")

            if entry_type == "task":
                section_parts.append(
                    f"- Task: {entry_data.get('task_description', 'N/A')} "
                    f"({entry_data.get('timestamp', 'N/A')})\n"
                    f"  Agents: {', '.join(entry_data.get('agents_used', []))}\n"
                    f"  Pipeline: {entry_data.get('pipeline', 'N/A')}\n"
                    f"  Result: {entry_data.get('result_status', 'N/A')}"
                )
            elif entry_type == "patch":
                section_parts.append(
                    f"- Patch: {entry_data.get('task_description', 'N/A')} "
                    f"({entry_data.get('timestamp', 'N/A')})\n"
                    f"  File: {entry_data.get('file', 'N/A')}\n"
                    f"  Reason: {entry_data.get('reason', 'N/A')}\n"
                    f"  Result: {entry_data.get('result_status', 'N/A')}\n"
                    f"  Diff preview: {entry_data.get('diff', '')[:200]}..."
                )
            elif entry_type == "decision":
                section_parts.append(
                    f"- Decision: {entry_data.get('task_description', 'N/A')} "
                    f"({entry_data.get('timestamp', 'N/A')})\n"
                    f"  Architecture Decision: {entry_data.get('architecture_decision', 'N/A')}\n"
                    f"  Context: {entry_data.get('context', 'N/A')}\n"
                    f"  Result: {entry_data.get('result', 'N/A')}"
                )
            else:
                section_parts.append(
                    f"- {entry_type.title()}: {entry_data.get('task_description', 'N/A')} "
                    f"({entry_data.get('timestamp', 'N/A')})\n"
                    f"  Data: {str(entry_data)[:200]}..."
                )

        return "\n".join(section_parts)

    def _format_rag_section(self, rag_results: list[dict[str, Any]]) -> str:
        """
        Форматирует секцию с контекстом из репозитория
        """
        section_parts = ["Repository context:"]

        for result in rag_results:
            content = result.get("content", "")
            file_path = result.get("file_path", "unknown")
            score = result.get("score", 0.0)

            section_parts.append(f"File: {file_path}\nScore: {score:.2f}\nContent:\n{content}\n")

        return "\n".join(section_parts)

    def _limit_context_tokens(self, context: str, max_tokens: int) -> str:
        """
        Ограничивает размер контекста по количеству токенов
        Простая эвристика: 1 токен ≈ 4 символа
        """
        approx_tokens = len(context) // 4

        if approx_tokens <= max_tokens:
            return context

        # Обрезаем контекст, стараясь сохранить целостность секций
        target_chars = max_tokens * 4
        if target_chars <= 0:
            return "[Context empty due to token limit]"

        # Пытаемся найти подходящее место для обрезки (между секциями)
        cut_position = target_chars
        # Ищем ближайший символ новой строки перед пределом
        while cut_position > 0 and context[cut_position] != "\n":
            cut_position -= 1

        # Если не нашли символ новой строки, просто обрезаем по пределу
        if cut_position == 0:
            cut_position = target_chars
            return context[:cut_position] + "\n\n[Context truncated due to token limit]"
        else:
            return context[:cut_position] + "\n\n[Context truncated due to token limit]"
