import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor


class _MockNode:
    def __init__(
        self,
        node_type,
        text_bytes,
        children=None,
        parent=None,
        start_point=None,
        start_byte=0,
        end_byte=None,
    ):
        self.type = node_type
        self.text = text_bytes
        self.children = children or []
        self.parent = parent
        self.start_point = start_point or (0, 0)
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else len(text_bytes)
        for child in self.children:
            child.parent = self


def _make_python_tree(source: str):
    src = source.encode("utf8")
    lines = source.split("\n")
    top_level = []
    byte_offset = 0

    for i, line in enumerate(lines):
        line_bytes = line.encode("utf8")
        line_start = byte_offset
        line_end = byte_offset + len(line_bytes)
        stripped = line.strip()

        if line and line[0] in (" ", "\t"):
            byte_offset = line_end + 1
            continue  # skip nested definitions
        if stripped.startswith("async def ") or stripped.startswith("def "):
            is_async = stripped.startswith("async def ")
            rest = stripped[len("async def ") if is_async else len("def ") :]
            name = rest.split("(")[0].strip()
            name_bytes = name.encode("utf8")
            col = line.index(name)
            ident = _MockNode(
                "identifier",
                name_bytes,
                start_point=(i, col),
                start_byte=line_start + col,
                end_byte=line_start + col + len(name_bytes),
            )
            func_type = "async_function_definition" if is_async else "function_definition"
            func = _MockNode(
                func_type,
                line_bytes,
                children=[ident],
                start_point=(i, 0),
                start_byte=line_start,
                end_byte=line_end,
            )
            top_level.append(func)
        elif stripped.startswith("class "):
            rest = stripped[len("class ") :]
            name = rest.split(":")[0].strip()
            name_bytes = name.encode("utf8")
            col = line.index(name)
            ident = _MockNode(
                "identifier",
                name_bytes,
                start_point=(i, col),
                start_byte=line_start + col,
                end_byte=line_start + col + len(name_bytes),
            )
            cls = _MockNode(
                "class_definition",
                line_bytes,
                children=[ident],
                start_point=(i, 0),
                start_byte=line_start,
                end_byte=line_end,
            )
            top_level.append(cls)

        byte_offset = line_end + 1  # +1 for the \n that split removed

    module = _MockNode(
        "module", src, children=top_level, start_point=(0, 0), start_byte=0, end_byte=len(src)
    )
    tree = MagicMock()
    tree.root_node = module
    return tree


def _run_with_mock(source: str, func):
    tree = _make_python_tree(source)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = Path(f.name)
    try:
        extractor = TreeSitterSymbolExtractor()
        with (
            patch("rag.symbol_extractor_tree_sitter.get_language_for_file", return_value="python"),
            patch("rag.symbol_extractor_tree_sitter.parse_file", return_value=tree),
        ):
            return extractor.extract_symbols(path)
    finally:
        path.unlink(missing_ok=True)


def test_async_python_function_extraction():
    source = """
async def fetch_data():
    pass

async def process():
    pass
"""
    symbols = _run_with_mock(source, None)

    assert len(symbols) == 2
    assert all(s.is_async for s in symbols)
    assert symbols[0].name == "fetch_data"
    assert symbols[1].name == "process"


def test_sync_python_function_extraction():
    source = """
def sync_function():
    pass

async def async_function():
    pass
"""
    symbols = _run_with_mock(source, None)

    assert len(symbols) == 2
    sync_func = next(s for s in symbols if s.name == "sync_function")
    async_func = next(s for s in symbols if s.name == "async_function")

    assert sync_func.is_async is False
    assert async_func.is_async is True


def test_python_class_extraction():
    source = """
class MyClass:
    def method(self):
        pass
"""
    symbols = _run_with_mock(source, None)

    assert len(symbols) == 1
    assert symbols[0].name == "MyClass"
    assert symbols[0].type == "class"
