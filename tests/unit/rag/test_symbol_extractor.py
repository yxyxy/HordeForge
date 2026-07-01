from pathlib import Path

from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor


def test_async_python_function_extraction():
    """Test that async Python functions are extracted correctly."""
    extractor = TreeSitterSymbolExtractor()
    source = """
async def fetch_data():
    pass

async def process():
    pass
"""
    symbols = extractor.extract_symbols(source, Path("test.py"), "python")

    assert len(symbols) == 2
    assert all(s.is_async for s in symbols)
    assert symbols[0].name == "fetch_data"
    assert symbols[1].name == "process"


def test_sync_python_function_extraction():
    """Test that sync Python functions are extracted correctly."""
    extractor = TreeSitterSymbolExtractor()
    source = """
def sync_function():
    pass

async def async_function():
    pass
"""
    symbols = extractor.extract_symbols(source, Path("test.py"), "python")

    assert len(symbols) == 2
    sync_func = next(s for s in symbols if s.name == "sync_function")
    async_func = next(s for s in symbols if s.name == "async_function")

    assert sync_func.is_async is False
    assert async_func.is_async is True


def test_python_class_extraction():
    """Test that Python classes are extracted correctly."""
    extractor = TreeSitterSymbolExtractor()
    source = """
class MyClass:
    def method(self):
        pass
"""
    symbols = extractor.extract_symbols(source, Path("test.py"), "python")

    assert len(symbols) == 1
    assert symbols[0].name == "MyClass"
    assert symbols[0].type == "class"
