"""
Tree-sitter parser module for code analysis and symbol extraction.
"""

import logging
from pathlib import Path

import tree_sitter
from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

# Supported languages and their file extensions
SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "c_sharp",
}

# Language parsers cache to improve performance
_PARSER_CACHE: dict[str, Parser] = {}


def initialize_language(language_name: str) -> Language | None:
    """
    Initialize a Tree-sitter language parser.

    Args:
        language_name: Name of the language (e.g., 'python', 'javascript')

    Returns:
        Language object or None if initialization fails
    """
    try:
        from tree_sitter import Language

        # Import the language dynamically and create Language object from PyCapsule
        if language_name == "python":
            import tree_sitter_python

            lang_capsule = tree_sitter_python.language()
        elif language_name == "javascript":
            import tree_sitter_javascript

            lang_capsule = tree_sitter_javascript.language()
        elif language_name == "typescript":
            import tree_sitter_typescript

            lang_capsule = tree_sitter_typescript.language()
        elif language_name == "java":
            import tree_sitter_java

            lang_capsule = tree_sitter_java.language()
        elif language_name == "go":
            import tree_sitter_go

            lang_capsule = tree_sitter_go.language()
        elif language_name == "rust":
            import tree_sitter_rust

            lang_capsule = tree_sitter_rust.language()
        elif language_name == "cpp":
            import tree_sitter_cpp

            lang_capsule = tree_sitter_cpp.language()
        elif language_name == "c":
            import tree_sitter_c

            lang_capsule = tree_sitter_c.language()
        elif language_name == "c_sharp":
            import tree_sitter_c_sharp

            lang_capsule = tree_sitter_c_sharp.language()
        else:
            logger.warning(f"Unsupported language: {language_name}")
            return None

        # Create Language object from the PyCapsule returned by tree-sitter language modules
        return Language(lang_capsule)
    except ImportError as e:
        logger.error(f"Failed to import Tree-sitter language parser for {language_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Tree-sitter language parser for {language_name}: {e}")
        return None


def get_parser(file_extension: str) -> Parser | None:
    """
    Get a cached parser for the given file extension.

    Args:
        file_extension: File extension (e.g., '.py', '.js')

    Returns:
        Parser object or None if unsupported language
    """
    if file_extension not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported file extension: {file_extension}")
        return None

    language_name = SUPPORTED_LANGUAGES[file_extension]

    # Check if parser is already cached
    if language_name in _PARSER_CACHE:
        return _PARSER_CACHE[language_name]

    # Initialize the language
    lang_obj = initialize_language(language_name)
    if lang_obj is None:
        return None

    # Create and cache the parser
    parser = Parser()
    parser.language = lang_obj
    _PARSER_CACHE[language_name] = parser

    logger.debug(f"Initialized parser for {language_name} language")
    return parser


def parse_file(file_path: str | Path) -> tree_sitter.Tree | None:
    """
    Parse a file using the appropriate Tree-sitter parser based on file extension.

    Args:
        file_path: Path to the file to parse

    Returns:
        Tree-sitter AST or None if parsing fails
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"File does not exist: {file_path}")
        return None

    file_extension = file_path.suffix.lower()
    parser = get_parser(file_extension)

    if parser is None:
        logger.warning(f"Cannot parse file {file_path} - unsupported language")
        return None

    try:
        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = parser.parse(source_code)
        logger.debug(
            f"Successfully parsed {file_path} with {len(tree.root_node.children)} top-level nodes"
        )
        return tree
    except TypeError as e:
        if "'PyCapsule' object is not callable" in str(e):
            logger.error(
                f"Tree-sitter library issue for {file_path}: {e}. This may be due to incompatible installation."
            )
            # Return None to allow fallback to other parsing methods
            return None
        else:
            logger.error(f"Type error parsing file {file_path}: {e}")
            return None
    except Exception as e:
        logger.error(f"Error parsing file {file_path}: {e}")
        return None


def get_language_for_file(file_path: str | Path) -> str | None:
    """
    Get the language name for a given file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Language name or None if unsupported
    """
    file_extension = Path(file_path).suffix.lower()
    return SUPPORTED_LANGUAGES.get(file_extension)


def reset_parser_cache():
    """
    Clear the parser cache. Useful for testing or when parsers need to be reinitialized.
    """
    global _PARSER_CACHE
    _PARSER_CACHE.clear()
    logger.debug("Parser cache cleared")
