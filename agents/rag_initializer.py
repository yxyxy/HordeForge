from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context

# Импорты для векторной базы данных и эмбеддингов
try:
    import qdrant_client
    from qdrant_client.http import models
    from sentence_transformers import SentenceTransformer
except ImportError:
    qdrant_client = None
    models = None
    SentenceTransformer = None

logger = logging.getLogger(__name__)


def setup_vector_db(config: dict[str, Any]) -> dict[str, Any]:
    """
    Инициализация векторной базы данных

    Args:
        config: Конфигурация векторной базы данных

    Returns:
        Результат инициализации
    """
    try:
        host = config.get("host", "localhost")
        port = config.get("port", 6333)

        if qdrant_client is None:
            raise ImportError("qdrant_client и sentence_transformers не установлены")

        client = qdrant_client.QdrantClient(host=host, port=port)

        # Проверяем соединение
        client.get_collections()

        return {"status": "ready", "client": client, "host": host, "port": port}
    except Exception as e:
        logger.error(f"Ошибка при инициализации векторной базы данных: {e}")
        return {"status": "failed", "error": str(e)}


def embed_documents(text: str) -> dict[str, Any]:
    """
    Генерация эмбеддингов для документа

    Args:
        text: Текст документа

    Returns:
        Результат эмбеддинга
    """
    try:
        if SentenceTransformer is None:
            raise ImportError("sentence_transformers не установлен")

        # Используем предобученную модель для генерации эмбеддингов
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embedding = model.encode([text])

        # Проверяем, является ли результат массивом numpy, и конвертируем его в список
        if hasattr(embedding[0], "tolist"):
            embedding_list = embedding[0].tolist()
        else:
            embedding_list = list(embedding[0])

        return {
            "status": "success",
            "embedding": embedding_list,  # преобразуем в список для сериализации
            "model": "all-MiniLM-L6-v2",
        }
    except Exception as e:
        logger.error(f"Ошибка при генерации эмбеддинга: {e}")
        return {"status": "failed", "error": str(e)}


def create_index(embeddings: list[list[float]]) -> dict[str, Any]:
    """
    Создание индекса для поиска

    Args:
        embeddings: Список эмбеддингов

    Returns:
        Результат создания индекса
    """
    try:
        if not embeddings:
            return {"status": "failed", "error": "Нет эмбеддингов для создания индекса"}

        if qdrant_client is None:
            raise ImportError("qdrant_client не установлен")

        # Создаем клиент для локальной Qdrant базы
        client = qdrant_client.QdrantClient(":memory:")  # используем in-memory для MVP

        collection_name = "hordeforge_docs"

        # Удаляем коллекцию если она существует
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass  # коллекция может не существовать

        # Создаем новую коллекцию
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
        )

        # Добавляем векторы в коллекцию
        points = []
        for idx, embedding in enumerate(embeddings):
            points.append(
                models.PointStruct(id=idx, vector=embedding, payload={"doc_id": f"doc_{idx}"})
            )

        if points:
            client.upsert(collection_name=collection_name, points=points)

        return {
            "status": "ready",
            "index_id": collection_name,
            "vector_count": len(points),
            "dimension": len(embeddings[0]) if embeddings else 0,
        }
    except Exception as e:
        logger.error(f"Ошибка при создании индекса: {e}")
        return {"status": "failed", "error": str(e)}


from agents.base import BaseAgent


class RagInitializer(BaseAgent):
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

        # Инициализируем векторную базу данных
        db_config = {
            "host": context.get("vector_db_host", "localhost"),
            "port": context.get("vector_db_port", 6333),
        }

        db_result = setup_vector_db(db_config)
        if db_result["status"] != "ready":
            logger.warning(f"Не удалось инициализировать векторную базу: {db_result.get('error')}")

        # Генерируем эмбеддинги для документов
        embeddings = []
        for doc in documents[:10]:  # Ограничиваем количество для MVP
            try:
                with open(Path(doc["path"]), encoding="utf-8") as f:
                    content = f.read()[:100]  # Ограничиваем размер документа

                embed_result = embed_documents(content)
                if embed_result["status"] == "success":
                    embeddings.append(embed_result["embedding"])
            except Exception as e:
                logger.error(f"Ошибка при обработке документа {doc['path']}: {e}")

        # Создаем индекс
        index_result = create_index(embeddings)
        if index_result["status"] != "ready":
            logger.warning(f"Не удалось создать индекс: {index_result.get('error')}")

        rag_index = {
            "index_id": "rag_index_v1",
            "documents_count": len(documents),
            "documents": documents,
            "source_repo": repository_metadata.get("full_name", "unknown"),
            "deterministic": True,
            "vector_db_status": db_result["status"],
            "embeddings_count": len(embeddings),
            "index_status": index_result["status"],
            "index_info": index_result if index_result["status"] == "ready" else None,
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="rag_index",
            artifact_content=rag_index,
            reason="Lightweight deterministic docs index built for MVP runtime.",
            confidence=0.88,
            logs=[
                f"Indexed {len(documents)} documents from {docs_dir.as_posix()}.",
                f"Created embeddings for {len(embeddings)} documents.",
                f"Vector DB status: {db_result['status']}",
                f"Index status: {index_result['status']}",
            ],
            next_actions=["memory_agent"],
        )
