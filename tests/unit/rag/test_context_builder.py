from unittest.mock import Mock

from rag.context_builder import ContextBuilder


def test_build_agent_context_includes_memory():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    # Настроим возвращаемые значения для ретриверов
    mock_memory_retriever.search_memory.return_value = [
        {
            "payload": {
                "type": "task",
                "task_description": "Fix authentication bug",
                "timestamp": "2024-01-15T10:00:00",
                "agents_used": ["planner", "code_generator", "review"],
                "result_status": "MERGED",
            }
        }
    ]

    mock_rag_retriever.retrieve.return_value = [
        {"content": "def validate_user():\n    pass", "file_path": "auth.py", "score": 0.95}
    ]

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("fix authentication")

    # Assert
    assert "Previous solutions:" in context
    assert "Fix authentication bug" in context
    assert "Repository context:" in context
    assert "def validate_user():" in context
    assert "auth.py" in context


def test_build_agent_context_handles_empty_memory():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    mock_memory_retriever.search_memory.return_value = []
    mock_rag_retriever.retrieve.return_value = [
        {"content": "def validate_user():\n    pass", "file_path": "auth.py", "score": 0.95}
    ]

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("fix authentication")

    # Assert
    assert "Previous solutions:" not in context
    assert "Repository context:" in context
    assert "def validate_user():" in context


def test_build_agent_context_handles_empty_rag():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    mock_memory_retriever.search_memory.return_value = [
        {
            "payload": {
                "type": "patch",
                "task_description": "Add validation",
                "timestamp": "2024-01-10T10:00:00",
                "file": "auth.py",
                "diff": "added validation",
                "result_status": "SUCCESS",
            }
        }
    ]

    mock_rag_retriever.retrieve.return_value = []

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("add validation")

    # Assert
    assert "Previous solutions:" in context
    assert "Add validation" in context
    assert "Repository context:" not in context


def test_build_agent_context_formats_patch_entries():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    mock_memory_retriever.search_memory.return_value = [
        {
            "payload": {
                "type": "patch",
                "task_description": "Fix login validation",
                "timestamp": "2024-01-15T10:00:00",
                "file": "auth.py",
                "diff": "Added null check in validate_user()",
                "reason": "Prevent null pointer exception",
                "result_status": "MERGED",
            }
        }
    ]

    mock_rag_retriever.retrieve.return_value = []

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("fix login")

    # Assert
    assert "Previous solutions:" in context
    assert "Fix login validation" in context
    assert "auth.py" in context
    assert "Prevent null pointer exception" in context
    assert "Added null check" in context


def test_build_agent_context_formats_decision_entries():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    mock_memory_retriever.search_memory.return_value = [
        {
            "payload": {
                "type": "decision",
                "task_description": "Choose auth method",
                "timestamp": "2024-01-10T10:00:00",
                "architecture_decision": "Use JWT tokens",
                "context": "Need secure authentication with minimal server state",
                "result": "Selected PyJWT library",
            }
        }
    ]

    mock_rag_retriever.retrieve.return_value = []

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("authentication")

    # Assert
    assert "Previous solutions:" in context
    assert "Choose auth method" in context
    assert "Use JWT tokens" in context
    assert "Need secure authentication" in context
    assert "Selected PyJWT library" in context


def test_limit_context_tokens():
    # Arrange
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    # Создадим длинный контекст
    long_content = "This is a very long content. " * 1000  # ~30k characters

    mock_memory_retriever.search_memory.return_value = []
    mock_rag_retriever.retrieve.return_value = [
        {"content": long_content, "file_path": "large_file.py", "score": 0.95}
    ]

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    # Act
    context = context_builder.build_agent_context("test", max_tokens=500)

    # Assert
    # Контекст должен быть ограничен примерно до 500 токенов (~2000 символов)
    assert len(context) <= 2500  # с учетом некоторого запаса
    assert "[Context truncated due to token limit]" in context


def test_format_memory_section():
    # Тестирование внутреннего метода форматирования секции памяти
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    memory_results = [
        {
            "payload": {
                "type": "task",
                "task_description": "Test task",
                "timestamp": "2024-01T0:00:00",
                "agents_used": ["test_agent"],
                "result_status": "SUCCESS",
                "pipeline": "test_pipeline",
            }
        }
    ]

    result = context_builder._format_memory_section(memory_results)

    assert "Previous solutions:" in result
    assert "Test task" in result
    assert "test_agent" in result
    assert "SUCCESS" in result
    assert "test_pipeline" in result


def test_format_rag_section():
    # Тестирование внутреннего метода форматирования RAG секции
    mock_memory_retriever = Mock()
    mock_rag_retriever = Mock()

    context_builder = ContextBuilder(mock_memory_retriever, mock_rag_retriever)

    rag_results = [{"content": "test content", "file_path": "test.py", "score": 0.85}]

    result = context_builder._format_rag_section(rag_results)

    assert "Repository context:" in result
    assert "test.py" in result
    assert "test content" in result
    assert "0.85" in result
