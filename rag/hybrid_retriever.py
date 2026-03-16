import logging

from rag.keyword_index import KeywordIndex
from rag.vector_store import QdrantStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Implements hybrid search combining vector similarity and keyword matching.
    Uses Reciprocal Rank Fusion (RRF) to combine results from both approaches.
    """

    def __init__(self, vector_store: QdrantStore, keyword_index: KeywordIndex):
        """
        Initialize the hybrid retriever with vector store and keyword index.

        Args:
            vector_store: Instance of QdrantStore for vector search
            keyword_index: Instance of KeywordIndex for keyword search
        """
        self.vector_store = vector_store
        self.keyword_index = keyword_index

    def search(
        self, query: str, limit: int = 10, alpha: float = 0.5, collection_name: str = "repo_chunks"
    ) -> list[dict]:
        """
        Perform hybrid search combining vector and keyword results.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            alpha: Weight for balancing vector vs keyword search (0.0 = keyword only, 1.0 = vector only)
            collection_name: Name of the collection to search in vector store

        Returns:
            List of combined results with scores
        """
        # Generate embedding for the query
        query_embeddings = self.vector_store.embed_text([query])
        if not query_embeddings:
            raise ValueError("Could not generate embedding for query")

        query_vector = query_embeddings[0]

        # Perform vector search
        vector_results = self.vector_store.search(
            collection_name=collection_name, query_vector=query_vector, limit=limit
        )

        # Perform keyword search
        keyword_results = self.keyword_index.search(query, limit=limit)

        # Combine results using weighted reciprocal rank fusion
        combined_results = self._merge_results(
            vector_results, keyword_results, alpha=alpha, limit=limit
        )

        return combined_results

    def _merge_results(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        alpha: float = 0.5,
        limit: int = 10,
    ) -> list[dict]:
        """
        Merge vector and keyword search results using Reciprocal Rank Fusion (RRF).

        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            alpha: Weight for vector results (1-alpha for keyword results)
            limit: Maximum number of results to return

        Returns:
            Merged and ranked results
        """
        # Create a mapping of doc_id to its position in each result list
        vector_rank_map = {res["id"]: idx + 1 for idx, res in enumerate(vector_results)}
        keyword_rank_map = {res["id"]: idx + 1 for idx, res in enumerate(keyword_results)}

        # Get all unique document IDs
        all_doc_ids = set(vector_rank_map.keys()) | set(keyword_rank_map.keys())

        # Calculate RRF scores for each document
        scored_docs = []
        for doc_id in all_doc_ids:
            # Calculate reciprocal rank scores
            vector_score = 0
            if doc_id in vector_rank_map:
                # Use the original vector similarity score weighted by alpha
                original_score = next((r["score"] for r in vector_results if r["id"] == doc_id), 0)
                vector_score = alpha * original_score

            keyword_score = 0
            if doc_id in keyword_rank_map:
                # Use RRF formula for keyword ranking: 1 / (k + rank)
                # where k is a smoothing constant (typically 60)
                k = 60
                rank = keyword_rank_map[doc_id]
                keyword_score = (1 - alpha) * (1.0 / (k + rank))

            # Combined score
            combined_score = vector_score + keyword_score

            # Find the document content (prefer vector result if available, otherwise keyword)
            doc_content = None
            doc_metadata = {}

            vector_result = next((r for r in vector_results if r["id"] == doc_id), None)
            keyword_result = next((r for r in keyword_results if r["id"] == doc_id), None)

            if vector_result:
                doc_content = vector_result.get("payload", {}).get("content", "")
                doc_metadata = vector_result.get("payload", {})
            elif keyword_result:
                doc_content = keyword_result.get("content", "")
                doc_metadata = keyword_result.get("metadata", {})

            scored_docs.append(
                {
                    "id": doc_id,
                    "score": combined_score,
                    "content": doc_content,
                    "metadata": doc_metadata,
                    "source_type": "hybrid",
                }
            )

        # Sort by combined score in descending order
        scored_docs.sort(key=lambda x: x["score"], reverse=True)

        # Return top results up to the limit
        return scored_docs[:limit]


def create_hybrid_retriever(
    host: str = "localhost", port: int = 6333, collection_name: str = "repo_chunks"
) -> HybridRetriever:
    """
    Factory function to create a hybrid retriever with initialized components.

    Args:
        host: Qdrant server host
        port: Qdrant server port
        collection_name: Name of the collection to use

    Returns:
        Initialized HybridRetriever instance
    """
    vector_store = QdrantStore(host=host, port=port)

    # Check if collection exists, create if it doesn't
    if not vector_store.collection_exists(collection_name):
        vector_store.create_collection(collection_name)

    keyword_index = KeywordIndex()

    return HybridRetriever(vector_store=vector_store, keyword_index=keyword_index)
