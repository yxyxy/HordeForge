import ast
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Symbol:
    """
    Represents a code symbol (class, function, method) extracted from Python code.
    """

    name: str
    type: str  # 'class', 'function', 'method'
    line_number: int
    docstring: str | None = None
    parameters: list[str] = None
    decorators: list[str] = None
    class_name: str | None = None  # For methods, indicates the parent class
    return_annotation: str | None = None
    is_async: bool = False

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.decorators is None:
            self.decorators = []


class SymbolExtractor(ast.NodeVisitor):
    """
    Extracts symbols (classes, functions, methods) from Python code using AST parsing.
    """

    def __init__(self):
        self.symbols: list[Symbol] = []
        self.current_class: str | None = None

    def extract_symbols(self, file_path: str | Path) -> list[Symbol]:
        """
        Extract symbols from a Python file.

        Args:
            file_path: Path to the Python file to analyze

        Returns:
            List[Symbol]: List of extracted symbols
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")

        if file_path.suffix != ".py":
            raise ValueError(f"File is not a Python file: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as file:
                content = file.read()

            tree = ast.parse(content, filename=str(file_path))
            self.visit(tree)

            return self.symbols
        except SyntaxError as e:
            logger.error(f"Syntax error in file {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error extracting symbols from {file_path}: {e}")
            raise

    def visit_ClassDef(self, node: ast.ClassDef):
        """
        Visit a class definition node and extract its information.
        """
        # Store the current class name to identify methods
        previous_class = self.current_class
        self.current_class = node.name

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Create symbol for the class
        class_symbol = Symbol(
            name=node.name,
            type="class",
            line_number=node.lineno,
            docstring=docstring,
            decorators=decorators,
        )

        self.symbols.append(class_symbol)

        # Visit child nodes (methods, nested classes, etc.)
        self.generic_visit(node)

        # Restore previous class context
        self.current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """
        Visit a function or method definition node and extract its information.
        """
        # Determine if this is a method (inside a class) or a function
        symbol_type = "method" if self.current_class else "function"

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract parameters
        parameters = []
        args = node.args

        # Regular arguments
        for arg in args.args:
            if arg.arg != "self":  # Skip 'self' for methods
                parameters.append(arg.arg)

        # *args
        if args.vararg:
            parameters.append(f"*{args.vararg.arg}")

        # Keyword-only arguments
        for arg in args.kwonlyargs:
            parameters.append(arg.arg)

        # **kwargs
        if args.kwarg:
            parameters.append(f"**{args.kwarg.arg}")

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Extract return annotation
        return_annotation = None
        if node.returns:
            return_annotation = ast.unparse(node.returns)

        # Create symbol
        symbol = Symbol(
            name=node.name,
            type=symbol_type,
            line_number=node.lineno,
            docstring=docstring,
            parameters=parameters,
            decorators=decorators,
            class_name=self.current_class,
            return_annotation=return_annotation,
            is_async=False,
        )

        self.symbols.append(symbol)

        # Don't visit child nodes for functions to avoid extracting nested functions
        # If we want to extract nested functions, we would call self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """
        Visit an async function definition node and extract its information.
        """
        # This is very similar to visit_FunctionDef but marks the function as async
        symbol_type = "method" if self.current_class else "function"

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract parameters
        parameters = []
        args = node.args

        # Regular arguments
        for arg in args.args:
            if arg.arg != "self":  # Skip 'self' for methods
                parameters.append(arg.arg)

        # *args
        if args.vararg:
            parameters.append(f"*{args.vararg.arg}")

        # Keyword-only arguments
        for arg in args.kwonlyargs:
            parameters.append(arg.arg)

        # **kwargs
        if args.kwarg:
            parameters.append(f"**{args.kwarg.arg}")

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Extract return annotation
        return_annotation = None
        if node.returns:
            return_annotation = ast.unparse(node.returns)

        # Create symbol
        symbol = Symbol(
            name=node.name,
            type=symbol_type,
            line_number=node.lineno,
            docstring=docstring,
            parameters=parameters,
            decorators=decorators,
            class_name=self.current_class,
            return_annotation=return_annotation,
            is_async=True,
        )

        self.symbols.append(symbol)


def extract_symbols_from_file(file_path: str | Path) -> list[Symbol]:
    """
    Convenience function to extract symbols from a file.

    Args:
        file_path: Path to the Python file to analyze

    Returns:
        List[Symbol]: List of extracted symbols
    """
    extractor = SymbolExtractor()
    return extractor.extract_symbols(file_path)
