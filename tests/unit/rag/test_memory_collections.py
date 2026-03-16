import pytest

from rag.memory_collections import (
    DecisionEntry,
    MemoryEntry,
    MemoryType,
    PatchEntry,
    TaskEntry,
    create_memory_entry,
)


def test_task_entry_schema():
    # Arrange & Act
    entry = TaskEntry(
        task_description="Fix authentication bug",
        pipeline="feature_pipeline",
        agents_used=["planner", "code_generator", "review"],
        result_status="MERGED",
    )

    # Assert
    assert entry.type == MemoryType.TASK
    assert entry.task_description == "Fix authentication bug"
    assert len(entry.agents_used) == 3
    assert entry.pipeline == "feature_pipeline"
    assert entry.result_status == "MERGED"


def test_patch_entry_schema():
    # Act
    entry = PatchEntry(
        task_description="Fix auth bug",
        file="auth.py",
        diff="--- a/auth.py\n+++ b/auth.py",
        reason="null check missing",
    )

    # Assert
    assert entry.type == MemoryType.PATCH
    assert entry.file == "auth.py"
    assert entry.diff.startswith("---")
    assert entry.reason == "null check missing"


def test_decision_entry_schema():
    # Act
    entry = DecisionEntry(
        task_description="Choose auth library",
        architecture_decision="Use JWT tokens",
        context="Need secure authentication",
        result="Selected PyJWT",
    )

    # Assert
    assert entry.type == MemoryType.DECISION
    assert entry.architecture_decision == "Use JWT tokens"
    assert entry.context == "Need secure authentication"
    assert entry.result == "Selected PyJWT"


def test_memory_entry_to_dict():
    # Arrange
    entry = TaskEntry(
        task_description="Test task",
        pipeline="test_pipeline",
        agents_used=["test_agent"],
        result_status="SUCCESS",
    )

    # Act
    result_dict = entry.to_dict()

    # Assert
    assert result_dict["task_description"] == "Test task"
    assert result_dict["pipeline"] == "test_pipeline"
    assert result_dict["agents_used"] == ["test_agent"]
    assert result_dict["result_status"] == "SUCCESS"
    assert result_dict["type"] == "task"
    assert "timestamp" in result_dict
    assert "id" in result_dict


def test_memory_entry_from_dict():
    # Arrange
    data = {
        "task_description": "Test task",
        "pipeline": "test_pipeline",
        "agents_used": ["test_agent"],
        "result_status": "SUCCESS",
        "type": "task",
    }

    # Act
    entry = MemoryEntry.from_dict(data)

    # Assert
    assert isinstance(entry, TaskEntry)
    assert entry.task_description == "Test task"
    assert entry.pipeline == "test_pipeline"
    assert entry.result_status == "SUCCESS"


def test_create_memory_entry_factory():
    # Test task entry creation
    task_entry = create_memory_entry("task", task_description="Test task", pipeline="test")
    assert isinstance(task_entry, TaskEntry)
    assert task_entry.type == MemoryType.TASK

    # Test patch entry creation
    patch_entry = create_memory_entry("patch", file="test.py", diff="test diff")
    assert isinstance(patch_entry, PatchEntry)
    assert patch_entry.type == MemoryType.PATCH

    # Test decision entry creation
    decision_entry = create_memory_entry("decision", architecture_decision="test decision")
    assert isinstance(decision_entry, DecisionEntry)
    assert decision_entry.type == MemoryType.DECISION

    # Test with MemoryType enum
    task_entry_enum = create_memory_entry(MemoryType.TASK, task_description="Test task")
    assert isinstance(task_entry_enum, TaskEntry)


def test_patch_entry_from_dict():
    # Arrange
    data = {
        "task_description": "Fix bug",
        "file": "auth.py",
        "diff": "test diff",
        "reason": "missing validation",
        "type": "patch",
    }

    # Act
    entry = MemoryEntry.from_dict(data)

    # Assert
    assert isinstance(entry, PatchEntry)
    assert entry.file == "auth.py"
    assert entry.diff == "test diff"
    assert entry.reason == "missing validation"


def test_decision_entry_from_dict():
    # Arrange
    data = {
        "task_description": "Architecture decision",
        "architecture_decision": "Use microservices",
        "context": "System design",
        "result": "Approved",
        "type": "decision",
    }

    # Act
    entry = MemoryEntry.from_dict(data)

    # Assert
    assert isinstance(entry, DecisionEntry)
    assert entry.architecture_decision == "Use microservices"
    assert entry.context == "System design"
    assert entry.result == "Approved"


def test_invalid_memory_type():
    # Test invalid type raises error
    with pytest.raises(ValueError):
        MemoryEntry.from_dict({"type": "invalid_type"})

    with pytest.raises(ValueError):
        create_memory_entry("invalid_type")


def test_post_init_validations():
    # Test that TaskEntry enforces its type
    with pytest.raises(ValueError):
        TaskEntry(type=MemoryType.PATCH)

    # Test that PatchEntry enforces its type
    with pytest.raises(ValueError):
        PatchEntry(type=MemoryType.TASK)

    # Test that DecisionEntry enforces its type
    with pytest.raises(ValueError):
        DecisionEntry(type=MemoryType.TASK)
