import json
import logging
import re

logger = logging.getLogger(__name__)


class KeywordIndex:
    """
    Simple inverted index for keyword-based search in code files.
    Maps keywords to document IDs where they appear.
    """

    def __init__(self):
        self.inverted_index: dict[str, set[str]] = {}
        self.documents: dict[str, dict] = {}  # Maps doc_id to document content/metadata

    def tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into keywords using simple word boundaries.

        Args:
            text: Input text to tokenize

        Returns:
            List of tokens/keywords
        """
        # Use regex to extract alphanumeric tokens (words)
        tokens = re.findall(r"\b\w+\b", text.lower())
        return tokens

    def add_document(self, doc_id: str, content: str, metadata: dict = None) -> None:
        """
        Add a document to the index.

        Args:
            doc_id: Unique identifier for the document
            content: Content of the document to index
            metadata: Additional metadata about the document
        """
        if metadata is None:
            metadata = {}

        # Store document content and metadata
        self.documents[doc_id] = {"content": content, "metadata": metadata}

        # Tokenize content and update inverted index
        tokens = self.tokenize(content)
        for token in tokens:
            if token not in self.inverted_index:
                self.inverted_index[token] = set()
            self.inverted_index[token].add(doc_id)

    def remove_document(self, doc_id: str) -> None:
        """
        Remove a document from the index.

        Args:
            doc_id: ID of the document to remove
        """
        if doc_id not in self.documents:
            return

        # Find all tokens associated with this document and remove the doc_id
        content = self.documents[doc_id]["content"]
        tokens = self.tokenize(content)

        for token in tokens:
            if token in self.inverted_index:
                self.inverted_index[token].discard(doc_id)
                # Remove the token entry if no documents contain it anymore
                if not self.inverted_index[token]:
                    del self.inverted_index[token]

        # Remove document from documents dict
        del self.documents[doc_id]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search for documents containing the query terms.

        Args:
            query: Query string to search for
            limit: Maximum number of results to return

        Returns:
            List of documents with scores based on keyword matches
        """
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        # Find documents that contain any of the query tokens
        matched_docs = {}

        for token in query_tokens:
            if token in self.inverted_index:
                for doc_id in self.inverted_index[token]:
                    if doc_id not in matched_docs:
                        matched_docs[doc_id] = 0
                    # Increase score for each matching token
                    matched_docs[doc_id] += 1

        # Sort documents by score (descending)
        sorted_docs = sorted(matched_docs.items(), key=lambda x: x[1], reverse=True)

        # Prepare results with document content and metadata
        results = []
        for doc_id, score in sorted_docs[:limit]:
            doc_data = self.documents[doc_id]
            results.append(
                {
                    "id": doc_id,
                    "score": score,
                    "content": doc_data["content"],
                    "metadata": doc_data["metadata"],
                }
            )

        return results

    def save_to_file(self, filepath: str) -> None:
        """
        Save the index to a file.

        Args:
            filepath: Path to save the index
        """
        data = {
            "inverted_index": {k: list(v) for k, v in self.inverted_index.items()},
            "documents": self.documents,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, filepath: str) -> None:
        """
        Load the index from a file.

        Args:
            filepath: Path to load the index from
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        self.inverted_index = {k: set(v) for k, v in data["inverted_index"].items()}
        self.documents = data["documents"]
