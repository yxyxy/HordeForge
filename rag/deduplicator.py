class Deduplicator:
    """
    Класс для удаления дубликатов из различных типов данных
    """

    def __init__(self):
        pass

    def deduplicate_list(self, items: list[str]) -> list[str]:
        """
        Удаляет дубликаты из списка строк

        Args:
            items: Список строк

        Returns:
            Список уникальных строк в том же порядке
        """
        seen: set[str] = set()
        unique_items = []

        for item in items:
            if item not in seen:
                seen.add(item)
                unique_items.append(item)

        return unique_items

    def deduplicate_chunks(self, chunks: list[dict]) -> list[dict]:
        """
        Удаляет дубликаты из списка чанков

        Args:
            chunks: Список чанков с полями 'content', 'metadata'

        Returns:
            Список уникальных чанков в том же порядке
        """
        seen: set[str] = set()
        unique_chunks = []

        for chunk in chunks:
            content = chunk.get("content", "")
            # Используем хэш содержимого как уникальный идентификатор
            content_hash = hash(content)

            if content_hash not in seen:
                seen.add(content_hash)
                unique_chunks.append(chunk)

        return unique_chunks


def deduplicate(items):
    """
    Функция для дедупликации (экспорт для использования вне класса)

    Args:
        items: Список элементов для дедупликации

    Returns:
        Список уникальных элементов
    """
    if not items:
        return []

    # Если это список словарей (чанков), используем специальную логику
    if isinstance(items[0], dict):
        deduplicator = Deduplicator()
        return deduplicator.deduplicate_chunks(items)
    # Если это список строк, используем соответствующую логику
    elif isinstance(items[0], str):
        deduplicator = Deduplicator()
        return deduplicator.deduplicate_list(items)
    else:
        # Для других типов используем стандартное множество
        seen = set()
        unique_items = []
        for item in items:
            if item not in seen:
                seen.add(item)
                unique_items.append(item)
        return unique_items
