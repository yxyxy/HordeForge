from typing import List, Dict, Any
from .memory_store import MemoryStore


class MemoryRetriever:
    """
    Класс для извлечения информации из памяти агента
    """

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def search_memory(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Поиск похожих задач в памяти
        
        Args:
            query: Запрос для поиска
            limit: Количество результатов
            
        Returns:
            Список найденных записей
        """
        return self.memory_store.search_memory(query, limit)