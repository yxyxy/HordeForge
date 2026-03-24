"""
Test script for smart chunking implementation.
"""

import asyncio
from pathlib import Path

from rag.chunking import ChunkGenerator, CodeStructureAnalyzer, SmartChunker
from rag.models import Symbol
from rag.stages import ChunkingStage


def test_code_structure_analyzer():
    """Test the CodeStructureAnalyzer with sample code."""
    print("Testing CodeStructureAnalyzer...")

    analyzer = CodeStructureAnalyzer()

    # Sample Python code with functions and classes
    sample_code = '''
class MyClass:
    """A sample class."""
    
    def __init__(self, value):
        self.value = value
    
    def my_method(self, param1, param2):
        """A sample method."""
        return param1 + param2

def my_function(x, y):
    """A sample function."""
    result = x * y
    return result

def another_function(a, b, c=None):
    """Another sample function."""
    if c is None:
        c = 10
    return a + b + c
'''

    # Create mock symbols
    symbols = [
        Symbol(
            name="MyClass",
            type="class",
            file_path="test.py",
            line_number=2,
            code_content=sample_code.split("\n")[1:12],
        ),
        Symbol(
            name="__init__",
            type="method",
            file_path="test.py",
            line_number=5,
            class_name="MyClass",
            code_content=sample_code.split("\n")[4:7],
        ),
        Symbol(
            name="my_method",
            type="method",
            file_path="test.py",
            line_number=7,
            class_name="MyClass",
            code_content=sample_code.split("\n")[6:10],
        ),
        Symbol(
            name="my_function",
            type="function",
            file_path="test.py",
            line_number=12,
            code_content=sample_code.split("\n")[11:15],
        ),
        Symbol(
            name="another_function",
            type="function",
            file_path="test.py",
            line_number=16,
            code_content=sample_code.split("\n")[15:20],
        ),
    ]

    # Convert code content back to string for each symbol
    for _i, symbol in enumerate(symbols):
        if isinstance(symbol.code_content, list):
            symbol.code_content = "\n".join(symbol.code_content)

    # Analyze the structure
    elements = analyzer.analyze(Path("test.py"), symbols, sample_code)
    print(f"Found {len(elements)} structural elements")
    for element in elements:
        print(f"  - {element.type} {element.name} (lines {element.start_line}-{element.end_line})")
        if element.children:
            for child in element.children:
                print(f"    - child: {child.type} {child.name}")


def test_smart_chunker():
    """Test the SmartChunker with sample elements."""
    print("\nTesting SmartChunker...")

    chunker = SmartChunker(max_chunk_size=512, overlap_size=50)

    # Sample elements
    from rag.chunking import CodeElement

    elements = [
        CodeElement(
            name="MyClass",
            type="class",
            start_line=2,
            end_line=11,
            content='class MyClass:\n    """A sample class."""\n    \n    def __init__(self, value):\n        self.value = value\n    \n    def my_method(self, param1, param2):\n        """A sample method."""\n        return param1 + param2',
        ),
        CodeElement(
            name="my_function",
            type="function",
            start_line=12,
            end_line=14,
            content='def my_function(x, y):\n    """A sample function."""\n    result = x * y\n    return result',
        ),
        CodeElement(
            name="another_function",
            type="function",
            start_line=16,
            end_line=19,
            content='def another_function(a, b, c=None):\n    """Another sample function."""\n    if c is None:\n        c = 10\n    return a + b + c',
        ),
    ]

    chunks = chunker.create_chunks(elements, "test.py")
    print(f"Created {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(
            f"  - Chunk {i + 1}: {chunk.symbol_type} {chunk.symbol_name} (lines {chunk.start_line}-{chunk.end_line})"
        )
        print(f"    Size: {len(chunk.text.split())} words")


def test_chunk_generator():
    """Test the ChunkGenerator end-to-end."""
    print("\nTesting ChunkGenerator...")

    generator = ChunkGenerator(max_chunk_size=512, overlap_size=50)

    # Sample code and symbols
    sample_code = '''
class MyClass:
    """A sample class."""
    
    def __init__(self, value):
        self.value = value
    
    def my_method(self, param1, param2):
        """A sample method."""
        return param1 + param2

def my_function(x, y):
    """A sample function."""
    result = x * y
    return result

def another_function(a, b, c=None):
    """Another sample function."""
    if c is None:
        c = 10
    return a + b + c
'''

    symbols = [
        Symbol(
            name="MyClass",
            type="class",
            file_path="test.py",
            line_number=2,
            code_content='class MyClass:\n    """A sample class."""\n    \n    def __init__(self, value):\n        self.value = value\n    \n    def my_method(self, param1, param2):\n        """A sample method."""\n        return param1 + param2',
        ),
        Symbol(
            name="my_function",
            type="function",
            file_path="test.py",
            line_number=12,
            code_content='def my_function(x, y):\n    """A sample function."""\n    result = x * y\n    return result',
        ),
        Symbol(
            name="another_function",
            type="function",
            file_path="test.py",
            line_number=16,
            code_content='def another_function(a, b, c=None):\n    """Another sample function."""\n    if c is None:\n        c = 10\n    return a + b + c',
        ),
    ]

    chunks = generator.generate_chunks(Path("test.py"), symbols, sample_code)
    print(f"Generated {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(
            f"  - Chunk {i + 1}: {chunk.symbol_type} {chunk.symbol_name} (lines {chunk.start_line}-{chunk.end_line})"
        )
        print(f"    Size: {len(chunk.text.split())} words")


def test_chunking_stage_integration():
    """Test the integration with ChunkingStage."""
    print("\nTesting ChunkingStage integration...")

    stage = ChunkingStage(chunk_size=512, overlap=50, use_smart_chunking=True)

    # Sample code and symbols
    sample_code = '''
class MyClass:
    """A sample class."""
    
    def __init__(self, value):
        self.value = value
    
    def my_method(self, param1, param2):
        """A sample method."""
        return param1 + param2

def my_function(x, y):
    """A sample function."""
    result = x * y
    return result

def another_function(a, b, c=None):
    """Another sample function."""
    if c is None:
        c = 10
    return a + b + c
'''

    # Write sample code to a temporary file so the stage can read it
    test_file = Path("test_sample.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(sample_code)

    try:
        symbols = [
            Symbol(
                name="MyClass",
                type="class",
                file_path=str(test_file),
                line_number=2,
                code_content='class MyClass:\n    """A sample class."""\n    \n    def __init__(self, value):\n        self.value = value\n    \n    def my_method(self, param1, param2):\n        """A sample method."""\n        return param1 + param2',
            ),
            Symbol(
                name="my_function",
                type="function",
                file_path=str(test_file),
                line_number=12,
                code_content='def my_function(x, y):\n    """A sample function."""\n    result = x * y\n    return result',
            ),
            Symbol(
                name="another_function",
                type="function",
                file_path=str(test_file),
                line_number=16,
                code_content='def another_function(a, b, c=None):\n    """Another sample function."""\n    if c is None:\n        c = 10\n    return a + b + c',
            ),
        ]

        # Run the stage
        chunks = asyncio.run(stage.run(symbols))
        print(f"ChunkingStage created {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(
                f"  - Chunk {i + 1}: {chunk.symbol_type} {chunk.symbol_name} (lines {chunk.start_line}-{chunk.end_line})"
            )
            print(f"    Size: {len(chunk.text.split())} words")
    finally:
        # Clean up the test file
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    print("Starting tests for smart chunking implementation...\n")

    test_code_structure_analyzer()
    test_smart_chunker()
    test_chunk_generator()
    test_chunking_stage_integration()

    print("\nAll tests completed!")
