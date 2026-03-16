# tests/unit/agents/test_memory_agent.py
from agents.memory_agent import retrieve_context, setup_memory, store_context


class TestMemoryStorageSetup:
    """TDD: Memory Storage Setup"""

    def test_setup_memory_success(self):
        """TDD: Memory storage initialized"""
        # Arrange
        config = {"type": "json", "file_path": ".hordeforge_data/test_memory.json"}

        # Act
        result = setup_memory(config)

        # Assert
        assert result["status"] == "ready"

    def test_setup_memory_failure(self):
        """TDD: Memory storage failed"""
        # Arrange
        config = {"type": "invalid"}

        # Act
        result = setup_memory(config)

        # Assert
        assert result["status"] == "failed"


class TestContextRetrieval:
    """TDD: Context Retrieval"""

    def test_retrieve_context_success(self):
        """TDD: Context retrieved successfully"""
        # Arrange
        # First store a context
        context = {"data": "test_data", "context_id": "ctx_123"}
        store_result = store_context(context)
        assert store_result["status"] == "success"

        context_id = "ctx_123"

        # Act
        result = retrieve_context(context_id)

        # Assert
        assert result["status"] == "success"
        assert "context" in result

    def test_retrieve_context_not_found(self):
        """TDD: Context not found"""
        # Arrange
        context_id = "nonexistent"

        # Act
        result = retrieve_context(context_id)

        # Assert
        assert result["status"] == "not_found"


class TestContextStorage:
    """TDD: Context Storage"""

    def test_store_context_success(self):
        """TDD: Context stored successfully"""
        # Arrange
        context = {"data": "test"}

        # Act
        result = store_context(context)

        # Assert
        assert result["status"] == "success"
        assert "context_id" in result

    def test_store_context_failure(self):
        """TDD: Context storage failed"""
        # Arrange
        context = {}

        # Act
        result = store_context(context)

        # Assert
        assert result["status"] == "failed"
