import os
import tempfile

from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor

# Create a temporary Python file with sample code
sample_code = '''class MyClass:
    """A sample class."""
    
    def __init__(self, value):
        self.value = value
    
    def my_method(self):
        """A sample method."""
        return self.value

def my_function(x, y):
    """A sample function."""
    return x + y

async def async_function():
    """An async function."""
    pass'''

with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
    f.write(sample_code)
    temp_file = f.name

try:
    extractor = TreeSitterSymbolExtractor()
    symbols = extractor.extract_symbols(temp_file)

    print(f"Found {len(symbols)} symbols:")
    for symbol in symbols:
        print(f"- {symbol.type}: {symbol.name} at line {symbol.line_number}")
finally:
    os.unlink(temp_file)
