import logging
import time

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from rag.config import get_embedding_model, get_qdrant_host, get_qdrant_port, get_vector_store_mode

logger = logging.getLogger(__name__)

# Suppress verbose HTTP logging from httpx/qdrant_client
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)

# Use QDRANT_HOST env var, fallback to "qdrant" for Docker, "localhost" for local
QDRANT_HOST = get_qdrant_host()
QDRANT_PORT = get_qdrant_port()
DEFAULT_COLLECTION_NAME = "repo_chunks"
VECTOR_SIZE = 384  # Default size for FastEmbed models


class QdrantStore:
    """
    A wrapper class for Qdrant vector store operations.
    Handles connection, collection management, and basic CRUD operations.
    Supports in-memory buffering for efficient batch upserts.
    """

    def __init__(
        self,
        host: str = QDRANT_HOST,
        port: int = QDRANT_PORT,
        buffer_limit: int = 256,
        check_compatibility: bool = False,  # 🔥 Отключаем проверку версии
        mode: str = None,  # Can be 'local', 'host', or 'auto'
    ):
        """
        Initialize the QdrantStore with connection parameters.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            buffer_limit: Number of points to buffer before auto-flush (default 256)
            check_compatibility: Skip version compatibility check (for mismatched versions)
            mode: Vector store mode ('local', 'host', or 'auto'). If None, uses config value.
        """
        self.mode = mode or get_vector_store_mode()
        self.host = host
        self.port = port

        # Store original parameters for potential reconnection
        self._original_host = host
        self._original_port = port
        self._original_check_compatibility = check_compatibility

        # Determine if we should use in-memory mode based on the mode setting
        if self.mode == "local":
            # Use in-memory storage
            self.client = QdrantClient(":memory:", check_compatibility=check_compatibility)
        elif self.mode == "host":
            # Use host-based storage, but check if it's available
            try:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    check_compatibility=check_compatibility,  # 🔥 Критично для старых серверов
                )
                # Test connection
                self.client.get_collections()
            except Exception as e:
                logger.warning(f"Host Qdrant unavailable: {e}. Falling back to local mode.")
                self._switch_to_local_mode(check_compatibility)
        elif self.mode == "auto":
            # Try host mode first, fall back to local if unavailable
            try:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    check_compatibility=check_compatibility,  # 🔥 Критично для старых серверов
                )
                # Test connection
                self.client.get_collections()
            except Exception as e:
                logger.info(f"Auto mode: Host Qdrant unavailable: {e}. Using local mode.")
                self._switch_to_local_mode(check_compatibility)
        else:
            # Default to auto mode if invalid mode provided
            logger.warning(f"Invalid mode '{self.mode}', defaulting to 'auto' mode.")
            try:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    check_compatibility=check_compatibility,  # 🔥 Критично для старых серверов
                )
                # Test connection
                self.client.get_collections()
            except Exception as e:
                logger.info(f"Auto mode: Host Qdrant unavailable: {e}. Using local mode.")
                self._switch_to_local_mode(check_compatibility)

        self.embedder = TextEmbedding(model_name=get_embedding_model())
        self._buffer: list[dict] = []
        self._buffer_limit = buffer_limit
        self._total_indexed = 0

    def _switch_to_local_mode(self, check_compatibility: bool = False):
        """
        Switch to local in-memory mode, properly closing any existing client first.
        This ensures that no network connections remain active after fallback.
        """
        # If we have an existing client, close it properly to prevent lingering connections
        if hasattr(self, "client") and self.client is not None:
            try:
                # Close the existing client to ensure no network connections remain
                if hasattr(self.client, "_client"):
                    # For remote clients, try to close underlying connections
                    if hasattr(self.client._client, "close"):
                        self.client._client.close()
            except Exception as e:
                logger.warning(f"Error closing previous client: {e}")

        # Create a fresh in-memory client
        self.client = QdrantClient(":memory:", check_compatibility=check_compatibility)
        self.mode = "local"
        logger.info("Successfully switched to local in-memory mode")

    def get_client(self) -> QdrantClient:
        """
        Get the Qdrant client instance.

        Returns:
            QdrantClient: The initialized client
        """
        return self.client

    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name: Name of the collection to check

        Returns:
            bool: True if collection exists, False otherwise
        """
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = VECTOR_SIZE,
        distance: models.Distance = models.Distance.COSINE,
        indexing_threshold: int = 1000,
        hnsw_config: dict | None = None,
    ) -> bool:
        """
        Create a new collection in Qdrant with specified vector parameters.

        Args:
            collection_name: Name of the collection to create
            vector_size: Size of the vectors to store
            distance: Distance metric for similarity search
            indexing_threshold: Start indexing after this many points (lower = faster start)
            hnsw_config: HNSW index configuration (use {"m": 0} for faster ingestion)

        Returns:
            bool: True if collection was created, False if already existed
        """
        if self.collection_exists(collection_name):
            logger.info(f"Collection '{collection_name}' already exists")
            return False

        # Use default HNSW config if none provided
        if hnsw_config is None:
            hnsw_config = {"m": 16}  # Default balanced setting

        # Convert dict to HnswConfigDiff
        hnsw_config_diff = models.HnswConfigDiff(**hnsw_config)

        # Create collection with proper models
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=distance,
            ),
            hnsw_config=hnsw_config_diff,
        )

        # Tune optimizer for faster indexing (start indexing earlier)
        try:
            self.client.update_collection(
                collection_name=collection_name,
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=indexing_threshold,  # Default 20000 -> 1000
                ),
            )
        except Exception as e:
            logger.warning(f"Could not update optimizer config: {e}")

        logger.info(
            f"Created collection '{collection_name}' with vector size {vector_size} and HNSW config {hnsw_config}"
        )
        return True

    def get_collection(self, collection_name: str):
        """
        Get collection information from Qdrant.

        Args:
            collection_name: Name of the collection to retrieve

        Returns:
            CollectionInfo: Information about the collection
        """
        return self.client.get_collection(collection_name)

    def add_point(self, collection_name: str, point: dict) -> None:
        """
        Add a single point to the in-memory buffer. Auto-flushes when buffer is full.

        Args:
            collection_name: Name of the collection
            point: Single point to add (with id, vector, and payload)
        """
        self._buffer.append(point)
        logger.debug(f"Added point to buffer, current buffer size: {len(self._buffer)}")
        if len(self._buffer) >= self._buffer_limit:
            self.flush(collection_name)

    def flush(self, collection_name: str) -> int:
        """
        Flush the in-memory buffer to Qdrant.

        Args:
            collection_name: Name of the collection

        Returns:
            int: Number of points flushed
        """
        if not self._buffer:
            logger.debug("Buffer is empty, nothing to flush")
            return 0

        # Проверим существование коллекции с блокировкой для избежания гонки
        collection_ready = False
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                if self.collection_exists(collection_name):
                    collection_ready = True
                    break
                else:
                    logger.warning(
                        f"Collection '{collection_name}' does not exist, attempt {retry_count + 1}/{max_retries}"
                    )
                    time.sleep(0.1)  # Небольшая задержка перед повторной проверкой
                    retry_count += 1
            except Exception as e:
                logger.warning(
                    f"Error checking collection existence: {e}, attempt {retry_count + 1}/{max_retries}"
                )
                time.sleep(0.1)
                retry_count += 1

        if not collection_ready:
            logger.error(
                f"Collection '{collection_name}' does not exist after {max_retries} attempts, skipping flush"
            )
            return 0

        logger.debug(
            f"Flushing buffer with {len(self._buffer)} points to collection '{collection_name}'"
        )

        # Use smaller batches within the buffer for stability
        batch_size = self._buffer_limit
        flushed = 0

        for i in range(0, len(self._buffer), batch_size):
            batch = self._buffer[i : i + batch_size]
            # 🔥 Используем models.PointStruct для совместимости
            points = [
                models.PointStruct(
                    id=p.get("id"),
                    vector=p.get("vector"),
                    payload=p.get("payload", {}),
                )
                for p in batch
            ]
            logger.debug(f"Sending batch of {len(points)} points to Qdrant")
            try:
                # Используем wait=True для лучшей диагностики
                result = self.client.upsert(
                    collection_name=collection_name, points=points, wait=False
                )
                logger.debug(f"Upsert result: {result}")

                # Проверим результат апсерта
                if result is None:
                    logger.warning("Upsert returned None, this may indicate an issue")
                elif hasattr(result, "status"):
                    if result.status == "completed":
                        logger.debug("Upsert completed successfully")
                    else:
                        logger.debug(f"Upsert status: {result.status}")
                else:
                    logger.debug(f"Upsert result: {result}")
            except Exception as e:
                logger.error(f"Failed to upsert batch: {e}")
                logger.exception("Full traceback:")
                raise
            flushed += len(batch)

        self._total_indexed += flushed
        logger.info(f"Flushed {flushed} points (total indexed: {self._total_indexed})")
        self._buffer.clear()
        logger.debug("Buffer cleared after flush")
        return flushed

    def close(self, collection_name: str) -> int:
        """
        Flush remaining buffer and close. Call this when done indexing.

        Args:
            collection_name: Name of the collection

        Returns:
            int: Number of points flushed
        """
        return self.flush(collection_name)

    def upsert(self, collection_name: str, points: list[dict], batch_size: int = 100) -> None:
        """
        Upsert points into a collection (legacy method, use add_point + flush for better performance).

        Args:
            collection_name: Name of the collection
            points: List of points to upsert, each with id, vector, and payload
            batch_size: Number of points to process in each batch
        """
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        # Process in batches to handle large datasets efficiently
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            # 🔥 Используем models.PointStruct для совместимости
            points_struct = [
                models.PointStruct(
                    id=p.get("id"),
                    vector=p.get("vector"),
                    payload=p.get("payload", {}),
                )
                for p in batch
            ]
            self.client.upsert(collection_name=collection_name, points=points_struct)

        logger.info(f"Upserted {len(points)} points into collection '{collection_name}'")

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: models.Filter | None = None,
    ) -> list[dict]:
        """
        Search for similar vectors in the collection.

        Args:
            collection_name: Name of the collection to search
            query_vector: Vector to search for similar items
            limit: Maximum number of results to return
            filters: Optional filters to apply to the search

        Returns:
            List[Dict]: List of search results with scores and payloads
        """
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=filters,
        )

        # Format results to return a list of dictionaries
        formatted_results = []
        for result in results:
            formatted_results.append(
                {"id": result.id, "score": result.score, "payload": result.payload}
            )

        return formatted_results

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List[List[float]]: List of embedding vectors
        """
        embeddings = list(self.embedder.embed(texts))
        return [embedding.tolist() for embedding in embeddings]
