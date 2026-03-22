import pytest

from rag.deduplicator import Deduplicator, deduplicate


def test_deduplication_removes_duplicates():
    # Arrange
    chunks = [
        {"content": "def auth():", "score": 0.9},
        {"content": "def auth():", "score": 0.9},  # exact duplicate
        {"content": "def login():", "score": 0.8},
    ]

    # Act
    deduped = deduplicate(chunks)

    # Assert
    assert len(deduped) == 2
    assert deduped[0]["content"] == "def auth():"


def test_deduplicate_list_removes_duplicates():
    # Arrange
    items = ["item1", "item2", "item1", "item3"]

    # Act
    deduped = deduplicate(items)

    # Assert
    assert len(deduped) == 3
    assert deduped.count("item1") == 1


def test_deduplicator_class():
    # Arrange
    deduplicator = Deduplicator()
    chunks = [
        {"content": "def auth():", "score": 0.9},
        {"content": "def auth():", "score": 0.9},  # exact duplicate
        {"content": "def login():", "score": 0.8},
    ]

    # Act
    deduped = deduplicator.deduplicate_chunks(chunks)

    # Assert
    assert len(deduped) == 2
    assert deduped[0]["content"] == "def auth():"


if __name__ == "__main__":
    pytest.main([__file__])
