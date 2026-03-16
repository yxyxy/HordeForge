from .deduplicator import Deduplicator


class ContextCompressor:
    """
    Класс для сжатия контекста перед отправкой в LLM
    """

    def __init__(self):
        self.deduplicator = Deduplicator()

    def compress_context(self, text: str, max_tokens: int) -> str:
        """
        Сжимает текстовый контекст до заданного количества токенов

        Args:
            text: Входной текст для сжатия
            max_tokens: Максимальное количество токенов

        Returns:
            Сжатый текст
        """
        # Предполагаем, что один токен примерно равен 4 символам или 1 слову
        # Это приближенная оценка, на практике можно использовать токенизатор
        estimated_words = max_tokens * 0.75  # делаем небольшой запас

        # Разбиваем текст на строки для лучшего сохранения структуры
        lines = text.split("\n")

        # Удаляем дубликаты строк
        unique_lines = self.deduplicator.deduplicate_list(lines)

        # Обрезаем до нужного размера, стараясь сохранить целостность
        compressed_lines = []
        word_count = 0

        for line in unique_lines:
            line_word_count = len(line.split())

            if word_count + line_word_count <= estimated_words:
                compressed_lines.append(line)
                word_count += line_word_count
            else:
                # Если добавление всей строки превышает лимит,
                # пробуем добавить только часть строки
                remaining_tokens = int(estimated_words - word_count)
                if remaining_tokens > 0:
                    words = line.split()
                    partial_line = " ".join(words[:remaining_tokens])
                    compressed_lines.append(partial_line)
                    word_count += remaining_tokens
                break

        return "\n".join(compressed_lines)

    def compress_chunks(self, chunks: list[dict], max_tokens: int) -> list[dict]:
        """
        Сжимает список чанков, объединяя и укорачивая их

        Args:
            chunks: Список чанков с полями 'content', 'metadata'
            max_tokens: Максимальное количество токенов

        Returns:
            Сжатый список чанков
        """
        # Сначала удаляем дубликаты
        deduplicated_chunks = self.deduplicator.deduplicate_chunks(chunks)

        # Затем сжимаем, если все еще слишком большой
        total_content = ""
        compressed_chunks = []

        for chunk in deduplicated_chunks:
            content = chunk.get("content", "")
            # Проверяем, не превысим ли мы лимит
            if len(total_content) + len(content) < max_tokens * 4:  # приблизительно
                total_content += content + "\n"
                compressed_chunks.append(chunk)
            else:
                # Если превышаем, пробуем укоротить текущий чанк
                remaining_space = max_tokens * 4 - len(total_content)
                if remaining_space > 0:
                    shortened_content = content[: int(remaining_space * 0.8)]  # с запасом
                    chunk["content"] = shortened_content
                    compressed_chunks.append(chunk)
                break

        return compressed_chunks


def compress_context(text: str, max_tokens: int) -> str:
    """
    Функция для сжатия контекста (экспорт для использования вне класса)

    Args:
        text: Входной текст для сжатия
        max_tokens: Максимальное количество токенов

    Returns:
        Сжатый текст
    """
    compressor = ContextCompressor()
    return compressor.compress_context(text, max_tokens)
