"""Batch processing components for optimized embedding computation."""

import logging

import numpy as np
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# Попробуем импортировать sklearn, но не будем падать, если его нет
SKLEARN_AVAILABLE = False
normalize = None

try:
    from sklearn.preprocessing import normalize

    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("sklearn not available, using numpy normalization instead")
    SKLEARN_AVAILABLE = False
    normalize = None


class TextBuffer:
    """Buffer for accumulating texts for batch embedding computation."""

    def __init__(self, batch_size: int = 128):
        """
        Initialize the text buffer.

        Args:
            batch_size: Size of batches to yield when full
        """
        self.batch_size = batch_size
        self.buffer: list[tuple[str, dict]] = []  # List of (text, metadata) tuples

    def add_text(
        self, text: str, metadata: dict | None = None
    ) -> list[tuple[list[str], list[dict]]]:
        """
        Add a text to the buffer and return completed batches if buffer is full.

        Args:
            text: Text to add to buffer
            metadata: Optional metadata associated with the text

        Returns:
            List of (texts, metadatas) tuples representing completed batches
        """
        if metadata is None:
            metadata = {}

        self.buffer.append((text, metadata))
        completed_batches = []

        # Check if we have enough items to form a complete batch
        while len(self.buffer) >= self.batch_size:
            # Extract a batch of size batch_size
            batch_items = self.buffer[: self.batch_size]
            self.buffer = self.buffer[self.batch_size :]

            # Separate texts and metadatas
            texts, metadatas = zip(*batch_items, strict=False)
            completed_batches.append((list(texts), list(metadatas)))

        return completed_batches

    def get_remaining(self) -> tuple[list[str], list[dict]] | None:
        """
        Get any remaining items in the buffer that don't form a complete batch.

        Returns:
            Optional tuple of (texts, metadatas) for remaining items, or None if empty
        """
        if not self.buffer:
            return None

        texts, metadatas = zip(*self.buffer, strict=False)
        return list(texts), list(metadatas)

    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()


class BatchEmbedder:
    """Batch embedder with normalization support."""

    def __init__(self, embedder: TextEmbedding, normalize_vectors: bool = True):
        """
        Initialize the batch embedder.

        Args:
            embedder: TextEmbedding instance to use for computing embeddings
            normalize_vectors: Whether to normalize vectors after computation
        """
        self.embedder = embedder
        self.normalize_vectors = normalize_vectors

    def compute_embeddings(self, texts: list[str]) -> np.ndarray:
        """
        Compute embeddings for a batch of texts with optional normalization.

        Args:
            texts: List of texts to embed

        Returns:
            Numpy array of embeddings (num_texts, embedding_dim)
        """
        if not texts:
            return np.array([])

        # Compute embeddings using fastembed
        embeddings = list(self.embedder.embed(texts))
        embeddings_array = np.array(embeddings)

        # Apply normalization if requested
        if self.normalize_vectors:
            embeddings_array = self._normalize_embeddings(embeddings_array)

        return embeddings_array

    def _normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Normalize embeddings using L2 normalization.

        Args:
            embeddings: Array of embeddings to normalize (num_texts, embedding_dim)

        Returns:
            Normalized embeddings array
        """
        if embeddings.size == 0:
            return embeddings

        # Use sklearn's normalize function for L2 normalization if available
        if SKLEARN_AVAILABLE and normalize is not None:
            normalized = normalize(embeddings, norm="l2", axis=1)
        else:
            # Fallback to numpy-based L2 normalization
            # Calculate L2 norm for each row (axis=1)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            # Avoid division by zero
            norms = np.where(norms == 0, 1, norms)
            normalized = embeddings / norms

        return normalized

    def compute_and_process_batch(self, texts: list[str], metadatas: list[dict]) -> list[dict]:
        """
        Compute embeddings for a batch and return processed points ready for storage.

        Args:
            texts: List of texts to embed
            metadatas: List of metadata dictionaries corresponding to texts

        Returns:
            List of point dictionaries ready for insertion into vector store
        """
        from uuid import uuid4

        if not texts:
            return []

        # Compute embeddings
        embeddings = self.compute_embeddings(texts)
        points = []

        for text, metadata, embedding in zip(texts, metadatas, embeddings, strict=False):
            points.append(
                {
                    "id": str(uuid4()),
                    "vector": embedding.tolist(),
                    "payload": {"text": text, **metadata},
                }
            )

        return points
