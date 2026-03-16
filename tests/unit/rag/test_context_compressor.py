import pytest

from rag.context_compressor import ContextCompressor, compress_context


def test_compress_reduces_tokens():
    # Arrange
    large_context = "x " * 5000  # ~5000 tokens

    # Act
    compressed = compress_context(large_context, max_tokens=1000)

    # Assert
    assert len(compressed.split()) <= 1100  # with tolerance


def test_compress_preserves_structure():
    # Arrange
    test_context = "Line 1\nLine 2\nLine 3\nLine 2\nLine 4"  # Contains duplicate line

    # Act
    compressed = compress_context(test_context, max_tokens=100)

    # Assert
    # Should remove duplicate "Line 2" while preserving order
    lines = compressed.split("\n")
    assert lines.count("Line 2") == 1  # Only one instance of "Line 2"
    assert "Line 1" in lines
    assert "Line 3" in lines
    assert "Line 4" in lines


def test_compression_with_exact_limit():
    # Arrange
    compressor = ContextCompressor()
    test_text = "word1 word2 word3 word4 word5"

    # Act
    compressed = compressor.compress_context(test_text, max_tokens=3)

    # Assert
    word_count = len(compressed.split())
    assert word_count <= 3


if __name__ == "__main__":
    pytest.main([__file__])
