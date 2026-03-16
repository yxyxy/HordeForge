import logging

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import CollectionConfig, Distance, VectorParams

logger = logging.getLogger(__name__)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
DEFAULT_COLLECTION_NAME = "repo_chunks"
VECTOR_SIZE = 384  # Default size for FastEmbed models


class QdrantStore:
    """
    A wrapper class for Qdrant vector store operations.
    Handles connection, collection management, and basic CRUD operations.
    """

    def __init__(self, host: str = QDRANT_HOST, port: int = QDRANT_PORT):
        """
        Initialize the QdrantStore with connection parameters.

        Args:
            host: Qdrant server host
            port: Qdrant server port
        """
        self.host = host
        self.port = port
        self.client = QdrantClient(host=host, port=port)
        self.embedder = TextEmbedding()

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
    ) -> bool:
        """
        Create a new collection in Qdrant with specified vector parameters.

        Args:
            collection_name: Name of the collection to create
            vector_size: Size of the vectors to store
            distance: Distance metric for similarity search

        Returns:
            bool: True if collection was created, False if already existed
        """
        if self.collection_exists(collection_name):
            logger.info(f"Collection '{collection_name}' already exists")
            return False

        config = CollectionConfig(
            vectors=VectorParams(size=vector_size, distance=distance),
        )

        self.client.create_collection(collection_name=collection_name, vectors_config=config)
        logger.info(f"Created collection '{collection_name}' with vector size {vector_size}")
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

    def upsert(self, collection_name: str, points: list[dict], batch_size: int = 100) -> None:
        """
        Upsert points into a collection.

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
        search_filters = None
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
