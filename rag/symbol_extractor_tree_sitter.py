"""
Tree-sitter based symbol extractor for code analysis.
"""

import logging
from pathlib import Path

import tree_sitter
from tree_sitter import Node

from rag.symbol_extractor import Symbol
from rag.tree_sitter_parser import get_language_for_file, parse_file

logger = logging.getLogger(__name__)


class TreeSitterSymbolExtractor:
    """
    Extracts symbols (functions, classes, methods) from code files using Tree-sitter parsers.
    Supports multiple languages including Python, JavaScript, TypeScript, Java, Go, Rust, C++, C#.
    """

    def __init__(self):
        # Define Tree-sitter queries for different languages to extract symbols
        self.queries = {
            "python": {
                "functions": "(function_definition name: (identifier) @function_name)",
                "classes": "(class_definition name: (identifier) @class_name)",
                "methods": "(function_definition name: (identifier) @method_name)",
            },
            "javascript": {
                "functions": "(function_declaration name: (identifier) @function_name)",
                "arrow_functions": "(lexical_declaration (arrow_function) @arrow_function)",
                "classes": "(class_declaration name: (identifier) @class_name)",
                "methods": "(method_definition name: (property_identifier) @method_name)",
            },
            "typescript": {
                "functions": "(function_declaration name: (identifier) @function_name)",
                "arrow_functions": "(lexical_declaration (arrow_function) @arrow_function)",
                "classes": "(class_declaration name: (identifier) @class_name)",
                "methods": "(method_definition name: (property_identifier) @method_name)",
            },
            "java": {
                "functions": "(method_declaration name: (identifier) @function_name)",
                "classes": "(class_declaration name: (identifier) @class_name)",
                "interfaces": "(interface_declaration name: (identifier) @interface_name)",
            },
            "go": {
                "functions": "(function_declaration name: (identifier) @function_name)",
                "methods": "(method_declaration name: (field_identifier) @method_name)",
                "types": "(type_declaration (type_spec name: (identifier) @type_name))",
            },
            "rust": {
                "functions": "(function_item name: (identifier) @function_name)",
                "structs": "(struct_item name: (identifier) @struct_name)",
                "enums": "(enum_item name: (identifier) @enum_name)",
                "traits": "(trait_item name: (identifier) @trait_name)",
            },
            "cpp": {
                "functions": "(function_definition declarator: (function_declarator declarator: (identifier) @function_name))",
                "classes": "(class_specifier name: (type_identifier) @class_name)",
                "methods": "(function_definition declarator: (function_declarator declarator: (field_identifier) @method_name))",
            },
            "c": {
                "functions": "(function_definition declarator: (function_declarator declarator: (identifier) @function_name))",
            },
            "c_sharp": {
                "functions": "(method_declaration name: (identifier) @function_name)",
                "classes": "(class_declaration name: (identifier) @class_name)",
                "interfaces": "(interface_declaration name: (identifier) @interface_name)",
                "structs": "(struct_declaration name: (identifier) @struct_name)",
            },
        }

        # Extended queries for more detailed extraction
        self.extended_queries = {
            "python": """
                (function_definition
                    name: (identifier) @function_name
                    parameters: (parameters) @function_parameters
                    return_type: (_) @return_type)?
                (class_definition
                    name: (identifier) @class_name)?
                (decorated_definition
                    (function_definition
                        name: (identifier) @decorated_function_name
                        parameters: (parameters) @function_parameters
                        return_type: (_) @return_type)?)
            """,
            "javascript": """
                (function_declaration
                    name: (identifier) @function_name
                    parameters: (formal_parameters) @function_parameters)?
                (function_expression
                    name: (identifier) @function_name
                    parameters: (formal_parameters) @function_parameters)?
                (class_declaration
                    name: (identifier) @class_name)?
                (method_definition
                    name: (property_identifier) @method_name
                    parameters: (formal_parameters) @function_parameters)?
            """,
            "typescript": """
                (function_declaration
                    name: (identifier) @function_name
                    parameters: (formal_parameters) @function_parameters
                    return_type: (_) @return_type)?
                (class_declaration
                    name: (identifier) @class_name)?
                (method_definition
                    name: (property_identifier) @method_name
                    parameters: (formal_parameters) @function_parameters
                    return_type: (_) @return_type)?
            """,
            "java": """
                (method_declaration
                    name: (identifier) @function_name
                    parameters: (formal_parameters) @function_parameters
                    type: (_) @return_type)?
                (class_declaration
                    name: (identifier) @class_name)?
                (interface_declaration
                    name: (identifier) @interface_name)?
            """,
            "go": """
                (function_declaration
                    name: (identifier) @function_name
                    parameters: (parameter_list) @function_parameters
                    result: (_) @return_type)?
                (method_declaration
                    name: (field_identifier) @method_name
                    parameters: (parameter_list) @function_parameters
                    result: (_) @return_type)?
                (type_declaration
                    (type_spec
                        name: (identifier) @type_name))?
            """,
            "rust": """
                (function_item
                    name: (identifier) @function_name
                    parameters: (parameters) @function_parameters)?
                (struct_item
                    name: (identifier) @struct_name)?
                (enum_item
                    name: (identifier) @enum_name)?
                (trait_item
                    name: (identifier) @trait_name)?
            """,
            "cpp": """
                (function_definition
                    declarator: (function_declarator
                        declarator: (identifier) @function_name
                        parameters: (parameter_list) @function_parameters))?
                (class_specifier
                    name: (type_identifier) @class_name)?
            """,
            "c": """
                (function_definition
                    declarator: (function_declarator
                        declarator: (identifier) @function_name
                        parameters: (parameter_list) @function_parameters))?
            """,
            "c_sharp": """
                (method_declaration
                    name: (identifier) @function_name
                    parameters: (parameter_list) @function_parameters
                    return_type: (_) @return_type)?
                (class_declaration
                    name: (identifier) @class_name)?
                (interface_declaration
                    name: (identifier) @interface_name)?
                (struct_declaration
                    name: (identifier) @struct_name)?
            """,
        }

    def extract_symbols(self, file_path: str | Path) -> list[Symbol]:
        """
        Extract symbols from a file using Tree-sitter parser.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of Symbol objects representing extracted symbols
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return []

        # Determine language from file extension
        language = get_language_for_file(file_path)
        if not language:
            logger.warning(f"Unsupported file language: {file_path.suffix}")
            return []

        # Parse the file
        tree = parse_file(file_path)
        if not tree:
            logger.error(f"Failed to parse file: {file_path}")
            return []

        # Extract symbols based on language
        try:
            return self._extract_symbols_by_language(tree, language, file_path)
        except Exception as e:
            logger.error(f"Error extracting symbols from {file_path}: {e}")
            return []

    def _extract_symbols_by_language(
        self, tree: tree_sitter.Tree, language: str, file_path: Path
    ) -> list[Symbol]:
        """
        Extract symbols based on the specific language parser and queries.
        """
        symbols = []

        # Process based on language-specific patterns using direct tree traversal
        if language == "python":
            symbols.extend(self._extract_python_symbols_from_tree(tree.root_node, file_path))
        elif language == "javascript":
            symbols.extend(self._extract_javascript_symbols_from_tree(tree.root_node, file_path))
        elif language == "typescript":
            symbols.extend(self._extract_typescript_symbols_from_tree(tree.root_node, file_path))
        elif language == "java":
            symbols.extend(self._extract_java_symbols_from_tree(tree.root_node, file_path))
        elif language == "go":
            symbols.extend(self._extract_go_symbols_from_tree(tree.root_node, file_path))
        elif language == "rust":
            symbols.extend(self._extract_rust_symbols_from_tree(tree.root_node, file_path))
        elif language == "cpp":
            symbols.extend(self._extract_cpp_symbols_from_tree(tree.root_node, file_path))
        elif language == "c":
            symbols.extend(self._extract_c_symbols_from_tree(tree.root_node, file_path))
        elif language == "c_sharp":
            symbols.extend(self._extract_csharp_symbols_from_tree(tree.root_node, file_path))
        else:
            logger.warning(f"Language {language} not supported for symbol extraction")

        return symbols

    def _get_node_text(self, node: Node, source_bytes: bytes) -> str:
        """Extract text from a node in the source code."""
        return source_bytes[node.start_byte : node.end_byte].decode("utf8")

    def _get_docstring(self, node: Node, source_bytes: bytes) -> str | None:
        """Extract docstring/comment associated with a node."""
        # Look for comments before the node
        start_line = node.start_point[0]
        source_lines = source_bytes.decode("utf8").split("\n")

        # Check for docstring/comment in the lines before the node
        for i in range(start_line - 1, max(-1, start_line - 5), -1):  # Look up to 5 lines back
            if i >= 0:
                line = source_lines[i].strip()
                if (
                    line.startswith('"""')
                    or line.startswith("'''")
                    or line.startswith("//")
                    or line.startswith("/*")
                    or line.startswith("*")
                ):
                    return line.strip("\"'*/ ")

        return None

    def _get_decorators(self, node: Node, source_bytes: bytes) -> list[str]:
        """Extract decorators for a node (mainly for Python)."""
        decorators = []
        # For Python, decorators appear before the function/class definition
        # Find preceding sibling nodes that are decorators
        parent = node.parent
        if parent:
            for child in parent.children:
                if child.type == "decorated_definition" and child.contains(node):
                    # Find decorator nodes within the decorated definition
                    for inner_child in child.children:
                        if inner_child.type == "decorator":
                            decorator_text = self._get_node_text(inner_child, source_bytes)
                            decorators.append(decorator_text)
        return decorators

    def _get_parameters(self, node: Node, source_bytes: bytes) -> list[str]:
        """Extract parameters from a function/method node."""
        params = []
        for child in node.children:
            if child.type in ["parameters", "formal_parameters", "parameter_list"]:
                for param_child in child.children:
                    if param_child.type in [
                        "parameter",
                        "identifier",
                        "required_parameter",
                        "optional_parameter",
                    ]:
                        param_text = self._get_node_text(param_child, source_bytes)
                        # Clean up parameter text to just get the name
                        param_parts = param_text.split()
                        for part in param_parts:
                            if part.isidentifier():  # Simple check for identifier
                                params.append(part)
                                break
        return params

    def _walk_nodes(self, node):
        """Recursively walk through all nodes in the tree."""
        yield node
        for child in node.children:
            yield from self._walk_nodes(child)

    def _extract_python_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract Python-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function and class definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_definition":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    # Check if it's an async function
                    is_async = False
                    if len(node.children) > 0 and node.children[0].type == "identifier":
                        first_child_text = self._get_node_text(node.children[0], source_bytes)
                        if first_child_text == "async":
                            is_async = True

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                        is_async=is_async,
                    )
                    symbols.append(symbol)

            elif node.type == "class_definition":
                # Extract class information
                class_name_node = None
                # Find the identifier node for the class name
                for child in node.children:
                    if child.type == "identifier":
                        class_name_node = child
                        break

                if class_name_node:
                    class_name = self._get_node_text(class_name_node, source_bytes)
                    line_number = class_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(class_name_node, source_bytes)

                    symbol = Symbol(
                        name=class_name, type="class", line_number=line_number, docstring=docstring
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_javascript_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract JavaScript-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function and class definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_declaration":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "class_declaration":
                # Extract class information
                class_name_node = None
                # Find the identifier node for the class name
                for child in node.children:
                    if child.type == "identifier":
                        class_name_node = child
                        break

                if class_name_node:
                    class_name = self._get_node_text(class_name_node, source_bytes)
                    line_number = class_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(class_name_node, source_bytes)

                    symbol = Symbol(
                        name=class_name, type="class", line_number=line_number, docstring=docstring
                    )
                    symbols.append(symbol)

            elif node.type == "method_definition":
                # Extract method information
                method_name_node = None
                # Find the property_identifier node for the method name
                for child in node.children:
                    if child.type == "property_identifier":
                        method_name_node = child
                        break

                if method_name_node:
                    method_name = self._get_node_text(method_name_node, source_bytes)
                    line_number = method_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(method_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=method_name,
                        type="method",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_typescript_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract TypeScript-specific symbols by traversing the tree directly."""
        # Similar to JavaScript but with type annotations
        return self._extract_javascript_symbols_from_tree(root_node, file_path)

    def _extract_java_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract Java-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find method and class definitions
        for node in self._walk_nodes(root_node):
            if node.type == "method_declaration":
                # Extract method information
                method_name_node = None
                # Find the identifier node for the method name
                for child in node.children:
                    if child.type == "identifier":
                        method_name_node = child
                        break

                if method_name_node:
                    method_name = self._get_node_text(method_name_node, source_bytes)
                    line_number = method_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(method_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=method_name,
                        type="function",  # Using 'function' for consistency
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "class_declaration":
                # Extract class information
                class_name_node = None
                # Find the identifier node for the class name
                for child in node.children:
                    if child.type == "identifier":
                        class_name_node = child
                        break

                if class_name_node:
                    class_name = self._get_node_text(class_name_node, source_bytes)
                    line_number = class_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(class_name_node, source_bytes)

                    symbol = Symbol(
                        name=class_name, type="class", line_number=line_number, docstring=docstring
                    )
                    symbols.append(symbol)

            elif node.type == "interface_declaration":
                # Extract interface information
                interface_name_node = None
                # Find the identifier node for the interface name
                for child in node.children:
                    if child.type == "identifier":
                        interface_name_node = child
                        break

                if interface_name_node:
                    interface_name = self._get_node_text(interface_name_node, source_bytes)
                    line_number = interface_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(interface_name_node, source_bytes)

                    symbol = Symbol(
                        name=interface_name,
                        type="class",  # Treating interface as class for consistency
                        line_number=line_number,
                        docstring=docstring,
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_go_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract Go-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function and method definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_declaration":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "method_declaration":
                # Extract method information
                method_name_node = None
                # Find the field_identifier node for the method name
                for child in node.children:
                    if child.type == "field_identifier":
                        method_name_node = child
                        break

                if method_name_node:
                    method_name = self._get_node_text(method_name_node, source_bytes)
                    line_number = method_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(method_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=method_name,
                        type="method",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_rust_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract Rust-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function and struct definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_item":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "struct_item":
                # Extract struct information
                struct_name_node = None
                # Find the identifier node for the struct name
                for child in node.children:
                    if child.type == "identifier":
                        struct_name_node = child
                        break

                if struct_name_node:
                    struct_name = self._get_node_text(struct_name_node, source_bytes)
                    line_number = struct_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(struct_name_node, source_bytes)

                    symbol = Symbol(
                        name=struct_name,
                        type="class",  # Treating struct as class for consistency
                        line_number=line_number,
                        docstring=docstring,
                    )
                    symbols.append(symbol)

            elif node.type == "enum_item":
                # Extract enum information
                enum_name_node = None
                # Find the identifier node for the enum name
                for child in node.children:
                    if child.type == "identifier":
                        enum_name_node = child
                        break

                if enum_name_node:
                    enum_name = self._get_node_text(enum_name_node, source_bytes)
                    line_number = enum_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(enum_name_node, source_bytes)

                    symbol = Symbol(
                        name=enum_name,
                        type="class",  # Treating enum as class for consistency
                        line_number=line_number,
                        docstring=docstring,
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_cpp_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract C++-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function and class definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_definition":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier" and child.parent.type == "function_declarator":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "class_specifier":
                # Extract class information
                class_name_node = None
                # Find the type_identifier node for the class name
                for child in node.children:
                    if child.type == "type_identifier":
                        class_name_node = child
                        break

                if class_name_node:
                    class_name = self._get_node_text(class_name_node, source_bytes)
                    line_number = class_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(class_name_node, source_bytes)

                    symbol = Symbol(
                        name=class_name, type="class", line_number=line_number, docstring=docstring
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_c_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract C-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find function definitions
        for node in self._walk_nodes(root_node):
            if node.type == "function_definition":
                # Extract function information
                func_name_node = None
                # Find the identifier node for the function name
                for child in node.children:
                    if child.type == "identifier" and child.parent.type == "function_declarator":
                        func_name_node = child
                        break

                if func_name_node:
                    func_name = self._get_node_text(func_name_node, source_bytes)
                    line_number = func_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(func_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=func_name,
                        type="function",
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

        return symbols

    def _extract_csharp_symbols_from_tree(self, root_node, file_path: Path) -> list[Symbol]:
        """Extract C#-specific symbols by traversing the tree directly."""
        symbols = []
        source_bytes = root_node.text

        # Walk through all nodes in the tree to find method and class definitions
        for node in self._walk_nodes(root_node):
            if node.type == "method_declaration":
                # Extract method information
                method_name_node = None
                # Find the identifier node for the method name
                for child in node.children:
                    if child.type == "identifier":
                        method_name_node = child
                        break

                if method_name_node:
                    method_name = self._get_node_text(method_name_node, source_bytes)
                    line_number = method_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(method_name_node, source_bytes)
                    parameters = self._get_parameters(node, source_bytes)

                    symbol = Symbol(
                        name=method_name,
                        type="function",  # Using 'function' for consistency
                        line_number=line_number,
                        docstring=docstring,
                        parameters=parameters,
                    )
                    symbols.append(symbol)

            elif node.type == "class_declaration":
                # Extract class information
                class_name_node = None
                # Find the identifier node for the class name
                for child in node.children:
                    if child.type == "identifier":
                        class_name_node = child
                        break

                if class_name_node:
                    class_name = self._get_node_text(class_name_node, source_bytes)
                    line_number = class_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(class_name_node, source_bytes)

                    symbol = Symbol(
                        name=class_name, type="class", line_number=line_number, docstring=docstring
                    )
                    symbols.append(symbol)

            elif node.type == "interface_declaration":
                # Extract interface information
                interface_name_node = None
                # Find the identifier node for the interface name
                for child in node.children:
                    if child.type == "identifier":
                        interface_name_node = child
                        break

                if interface_name_node:
                    interface_name = self._get_node_text(interface_name_node, source_bytes)
                    line_number = interface_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(interface_name_node, source_bytes)

                    symbol = Symbol(
                        name=interface_name,
                        type="class",  # Treating interface as class for consistency
                        line_number=line_number,
                        docstring=docstring,
                    )
                    symbols.append(symbol)

            elif node.type == "struct_declaration":
                # Extract struct information
                struct_name_node = None
                # Find the identifier node for the struct name
                for child in node.children:
                    if child.type == "identifier":
                        struct_name_node = child
                        break

                if struct_name_node:
                    struct_name = self._get_node_text(struct_name_node, source_bytes)
                    line_number = struct_name_node.start_point[0] + 1  # Convert to 1-indexed
                    docstring = self._get_docstring(struct_name_node, source_bytes)

                    symbol = Symbol(
                        name=struct_name,
                        type="class",  # Treating struct as class for consistency
                        line_number=line_number,
                        docstring=docstring,
                    )
                    symbols.append(symbol)

        return symbols


def extract_symbols_from_file(file_path: str | Path) -> list[Symbol]:
    """
    Convenience function to extract symbols from a file using Tree-sitter.

    Args:
        file_path: Path to the file to analyze

    Returns:
        List of Symbol objects representing extracted symbols
    """
    extractor = TreeSitterSymbolExtractor()
    return extractor.extract_symbols(file_path)
