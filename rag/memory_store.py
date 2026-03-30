from __future__ import annotations

import uuid

from fastembed import TextEmbedding
from qdrant_client import QdrantClient

from rag.config import get_embedding_cache_dir, get_embedding_model


class MemoryStore:
    """
    Хранилище памяти агента для хранения истории решений и патчей
    """

    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self.embedder = TextEmbedding(
            model_name=get_embedding_model(),
            cache_dir=get_embedding_cache_dir(),
        )

    def add_memory(self, text: str, payload: dict) -> str:
        """
        Добавляет запись в память

        Args:
            text: Текст для эмбеддинга
            payload: Дополнительные данные

        Returns:
            ID созданной записи
        """
        vector = list(self.embedder.embed([text]))[0]
        point_id = str(uuid.uuid4())

        self.client.upsert(
            collection_name="agent_memory",
            points=[{"id": point_id, "vector": vector, "payload": payload}],
        )

        return point_id

    def search_memory(self, query: str, limit: int = 3) -> list[dict]:
        """
        Поиск похожих задач в памяти

        Args:
            query: Запрос для поиска
            limit: Количество результатов

        Returns:
            Список найденных записей
        """
        vector = list(self.embedder.embed([query]))[0]

        results = self.client.search(
            collection_name="agent_memory", query_vector=vector, limit=limit
        )

        return [{"payload": hit.payload, "score": hit.score} for hit in results]

    def create_collection(self) -> None:
        """
        Создает коллекцию для хранения памяти
        """
        from qdrant_client.http.models import Distance, VectorParams

        # Удаляем коллекцию, если она существует
        try:
            self.client.delete_collection("agent_memory")
        except Exception:
            pass  # Коллекция не существует, что нормально

        # Создаем новую коллекцию
        self.client.create_collection(
            collection_name="agent_memory",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    def get_memory_stats(self) -> dict:
        """
        Возвращает статистику по памяти

        Returns:
            Словарь со статистикой
        """
        try:
            count = self.client.count(collection_name="agent_memory").count
            return {"total_entries": count}
        except Exception:
            return {"total_entries": 0}
