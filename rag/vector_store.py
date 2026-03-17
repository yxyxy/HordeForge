import logging
import os

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# Suppress verbose HTTP logging from httpx/qdrant_client
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)

# Use QDRANT_HOST env var, fallback to "qdrant" for Docker, "localhost" for local
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
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
    ):
        """
        Initialize the QdrantStore with connection parameters.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            buffer_limit: Number of points to buffer before auto-flush (default 256)
        """
        self.host = host
        self.port = port
        self.client = QdrantClient(host=host, port=port)
        self.embedder = TextEmbedding()
        self._buffer: list[dict] = []
        self._buffer_limit = buffer_limit
        self._total_indexed = 0

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
        distance: Distance = Distance.COSINE,
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

        from qdrant_client.http.models import HnswConfigDiff

        # Convert dict to HnswConfigDiff if needed
        if isinstance(hnsw_config, dict):
            hnsw_config = HnswConfigDiff(**hnsw_config)

        # Use the sync client to create collection
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance,
            ),
            hnsw_config=hnsw_config,  # Apply HNSW configuration
        )

        # Tune optimizer for faster indexing (start indexing earlier)
        try:
            # Use the sync client to update collection
            self.client.update_collection(
                collection_name=collection_name,
                optimizer_config={
                    "indexing_threshold": indexing_threshold,  # Default 20000 -> 1000
                },
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
            return 0

        if not self.collection_exists(collection_name):
            logger.warning(f"Collection '{collection_name}' does not exist, skipping flush")
            return 0

        # Use smaller batches within the buffer for stability
        batch_size = self._buffer_limit
        flushed = 0

        for i in range(0, len(self._buffer), batch_size):
            batch = self._buffer[i : i + batch_size]
            self.client.upsert(collection_name=collection_name, points=batch)
            flushed += len(batch)

        self._total_indexed += flushed
        logger.info(f"Flushed {flushed} points (total indexed: {self._total_indexed})")
        self._buffer.clear()
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
            self.client.upsert(collection_name=collection_name, points=batch)

        logger.info(f"Upserted {len(points)} points into collection '{collection_name}'")

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
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

        # Convert filters to Qdrant format if provided
        if filters:
            # This is a simplified filter implementation
            # In a real scenario, you'd convert the dict to Qdrant Filter object
            pass

        results = self.client.search(
            collection_name=collection_name, query_vector=query_vector, limit=limit
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
