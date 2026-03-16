"""TDD: RAG Initializer Agent Tests"""

from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from agents.rag_initializer import RagInitializer, create_index, embed_documents, setup_vector_db


class TestVectorDBSetup:
    """TDD: Vector DB Setup"""

    def test_vector_db_init_success(self):
        """TDD: Vector DB initialized successfully"""
        # Arrange
        config = {"host": "localhost", "port": 6333}

        # Act
        with patch("agents.rag_initializer.qdrant_client") as mock_qdrant:
            mock_client = MagicMock()
            mock_qdrant.QdrantClient.return_value = mock_client
            mock_client.get_collections.return_value = True

            result = setup_vector_db(config)

        # Assert
        assert result["status"] == "ready"
        assert result["host"] == "localhost"
        assert result["port"] == 6333

    def test_vector_db_init_failure(self):
        """TDD: Vector DB connection failed"""
        # Arrange
        config = {"host": "invalid", "port": 6333}

        # Act
        with patch("agents.rag_initializer.qdrant_client") as mock_qdrant:
            mock_qdrant.QdrantClient.side_effect = Exception("Connection failed")

            result = setup_vector_db(config)

        # Assert
        assert result["status"] == "failed"
        assert "error" in result


class TestDocumentEmbedding:
    """TDD: Document Embedding"""

    def test_embed_document_success(self):
        """TDD: Document embedded successfully"""
        # Arrange
        text = "Sample document text"

        # Act
        with patch("agents.rag_initializer.SentenceTransformer") as mock_model:
            mock_instance = MagicMock()
            mock_instance.encode.return_value = [[0.1, 0.2, 0.3]]
            mock_model.return_value = mock_instance

            result = embed_documents(text)

        # Assert
        assert result["status"] == "success"
        assert "embedding" in result
        assert result["model"] == "all-MiniLM-L6-v2"

    def test_embed_document_failure(self):
        """TDD: Document embedding failed"""
        # Arrange
        text = ""

        # Act
        with patch("agents.rag_initializer.SentenceTransformer") as mock_model:
            mock_model.side_effect = ImportError("sentence_transformers not installed")

            result = embed_documents(text)

        # Assert
        assert result["status"] == "failed"
        assert "error" in result


class TestIndexCreation:
    """TDD: Index Creation"""

    def test_create_index_success(self):
        """TDD: Index created successfully"""
        # Arrange
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        # Act
        with patch("agents.rag_initializer.qdrant_client") as mock_qdrant:
            mock_client = MagicMock()
            mock_qdrant.QdrantClient.return_value = mock_client
            mock_client.get = lambda collection_name: None
            mock_client.delete_collection = lambda collection_name: None
            mock_client.create_collection = lambda **kwargs: None
            mock_client.upsert = lambda **kwargs: None

            result = create_index(embeddings)

        # Assert
        assert result["status"] == "ready"
        assert "index_id" in result
        assert result["vector_count"] == 2

    def test_create_index_failure(self):
        """TDD: Index creation failed"""
        # Arrange
        embeddings = []

        # Act
        result = create_index(embeddings)

        # Assert
        assert result["status"] == "failed"
        assert "error" in result


class TestRagInitializer:
    """TDD: RAG Initializer Agent"""

    def test_run_success(self):
        """TDD: RAG Initializer runs successfully"""
        # Arrange
        rag_initializer = RagInitializer()
        context = {"docs_dir": "docs"}

        # Act
        with patch.object(rag_initializer, "_collect_docs") as mock_collect:
            mock_collect.return_value = [
                {"path": "docs/test.md", "size_bytes": 100},
                {"path": "docs/readme.md", "size_bytes": 200},
            ]
            with patch("builtins.open", mock.mock_open(read_data="test content")):
                with patch("agents.rag_initializer.setup_vector_db") as mock_setup_db:
                    mock_setup_db.return_value = {"status": "ready"}
                    with patch("agents.rag_initializer.embed_documents") as mock_embed:
                        mock_embed.return_value = {"status": "success", "embedding": [0.1, 0.2]}
                        with patch("agents.rag_initializer.create_index") as mock_create_idx:
                            mock_create_idx.return_value = {
                                "status": "ready",
                                "index_id": "test_index",
                            }

                            result = rag_initializer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["type"] == "rag_index"


if __name__ == "__main__":
    pytest.main([__file__])
