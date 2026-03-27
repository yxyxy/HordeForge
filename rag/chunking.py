"""
Smart chunking module for RAG optimization.
Implements structural code analysis and intelligent chunking based on code symbols.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from logging_config import get_logger
from rag.models import Chunk, Symbol

logger = get_logger(__name__)


@dataclass
class CodeElement:
    """Represents a structural element in code (function, class, method, etc.)."""

    name: str
    type: str  # 'class', 'function', 'method', 'module'
    start_line: int
    end_line: int
    content: str
    parent: str | None = None  # For methods, indicates the parent class
    children: list["CodeElement"] = None  # Nested elements like methods in a class

    def __post_init__(self):
        if self.children is None:
            self.children = []


@dataclass
class StructuralContext:
    """Represents the structural context of a code element."""

    element: CodeElement
    siblings: list[CodeElement]  # Elements at the same level
    parent: CodeElement | None = None  # Parent element if nested
    children: list[CodeElement] = None  # Child elements if applicable

    def __post_init__(self):
        if self.children is None:
            self.children = []


class CodeStructureAnalyzer:
    """Analyzes code structure to identify hierarchical elements and relationships."""

    def __init__(self):
        pass

    def analyze(
        self, file_path: Path, symbols: list[Symbol], file_content: str
    ) -> list[CodeElement]:
        """
        Analyze the structure of code based on extracted symbols and file content.
        Creates a hierarchical representation of code elements.
        """
        logger.debug(f"Analyzing code structure for {file_path} with {len(symbols)} symbols")

        # Create code elements from symbols
        elements = []
        for symbol in symbols:
            if symbol.file_path == str(file_path):
                # Find the actual content for this symbol in the file
                content = self._extract_symbol_content(
                    file_content, symbol.line_number, symbol.code_content
                )
                element = CodeElement(
                    name=symbol.name,
                    type=symbol.type,
                    start_line=symbol.line_number,
                    end_line=self._estimate_end_line(content, symbol.line_number),
                    content=content,
                    parent=symbol.class_name if symbol.type == "method" else None,
                )
                elements.append(element)

        # Sort elements by start line to process in order
        elements.sort(key=lambda x: x.start_line)

        # Identify parent-child relationships (e.g., methods within classes)
        elements_with_hierarchy = self._build_hierarchy(elements)

        logger.debug(
            f"Identified {len(elements_with_hierarchy)} structural elements in {file_path}"
        )
        return elements_with_hierarchy

    def _extract_symbol_content(
        self, file_content: str, start_line: int, fallback_content: str
    ) -> str:
        """Extract content for a symbol based on its position in the file."""
        # Use the fallback content which should already be properly extracted
        return fallback_content

    def _estimate_end_line(self, code_content: str, start_line: int) -> int:
        """Estimate the end line of a code block."""
        lines = code_content.splitlines()
        return start_line + len(lines) - 1

    def _build_hierarchy(self, elements: list[CodeElement]) -> list[CodeElement]:
        """Build parent-child relationships between code elements."""
        # For now, we'll identify methods that belong to classes
        # In the future, this could be expanded to handle nested classes, etc.
        updated_elements = []
        element_map = {elem.name: elem for elem in elements}
        processed = set()

        for element in elements:
            if element.type == "method" and element.parent:
                # This is a method that belongs to a class
                parent_element = element_map.get(element.parent)
                if parent_element and parent_element.type == "class":
                    # Add this method as a child of the class
                    parent_element.children.append(element)
                    processed.add(element.name)
            elif element.name not in processed:
                updated_elements.append(element)

        # Add any remaining elements that weren't processed as children
        for element in elements:
            if element.name not in processed and element not in updated_elements:
                updated_elements.append(element)

        return updated_elements


class SmartChunker:
    """Implements intelligent chunking based on code structure and configurable parameters."""

    def __init__(self, max_chunk_size: int = 512, overlap_size: int = 50, min_chunk_size: int = 50):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

    def create_chunks(self, elements: list[CodeElement], file_path: str) -> list[Chunk]:
        """
        Create chunks from structural elements with consideration for code hierarchy and overlap.
        """
        logger.debug(f"Creating chunks from {len(elements)} elements in {file_path}")
        chunks = []

        # Process each top-level element
        for i, element in enumerate(elements):
            # Create a chunk for the main element
            chunk = self._create_element_chunk(element, file_path)
            if chunk:
                chunks.append(chunk)

            # If the element has children (like a class with methods), process them too
            if element.children:
                for child in element.children:
                    child_chunk = self._create_element_chunk(child, file_path)
                    if child_chunk:
                        chunks.append(child_chunk)

            # Add overlapping context if needed and available
            if i > 0 and self.overlap_size > 0:
                prev_element = elements[i - 1]
                overlap_chunk = self._create_overlap_chunk(prev_element, element, file_path)
                if overlap_chunk:
                    chunks.append(overlap_chunk)

        logger.debug(f"Created {len(chunks)} chunks from {file_path}")
        return chunks

    def _create_element_chunk(self, element: CodeElement, file_path: str) -> Chunk | None:
        """Create a chunk for a single structural element."""
        # Check if the element content is within our size limits
        content_lines = element.content.splitlines()
        if len(content_lines) == 0:
            return None

        # If the element is too large, we might need to split it further
        # For now, we'll create a chunk for the entire element
        chunk_id = str(uuid4())
        chunk = Chunk(
            id=chunk_id,
            text=element.content,
            file_path=file_path,
            start_line=element.start_line,
            end_line=element.end_line,
            symbol_name=element.name,
            symbol_type=element.type,
            metadata={
                "file_path": file_path,
                "symbol_name": element.name,
                "symbol_type": element.type,
                "line_number": element.start_line,
                "element_hierarchy": self._get_element_hierarchy(element),
                "is_complete_element": True,
            },
        )
        return chunk

    def _create_overlap_chunk(
        self, prev_element: CodeElement, curr_element: CodeElement, file_path: str
    ) -> Chunk | None:
        """Create a chunk that overlaps between two adjacent elements."""
        # Create overlap content by taking some lines from the end of the previous element
        # and some lines from the beginning of the current element
        prev_lines = prev_element.content.splitlines()
        curr_lines = curr_element.content.splitlines()

        # Take last N lines from previous element and first N lines from current element
        overlap_prev_lines = (
            prev_lines[-self.overlap_size // 2 :]
            if len(prev_lines) >= self.overlap_size // 2
            else prev_lines
        )
        overlap_curr_lines = (
            curr_lines[: self.overlap_size // 2]
            if len(curr_lines) >= self.overlap_size // 2
            else curr_lines
        )

        if not overlap_prev_lines and not overlap_curr_lines:
            return None

        overlap_content = "\n".join(overlap_prev_lines + overlap_curr_lines)
        if not overlap_content.strip():
            return None

        # Calculate approximate line numbers for the overlap
        start_line = max(
            prev_element.end_line - len(overlap_prev_lines) + 1, prev_element.start_line
        )
        end_line = min(curr_element.start_line + len(overlap_curr_lines) - 1, curr_element.end_line)

        chunk_id = str(uuid4())
        chunk = Chunk(
            id=chunk_id,
            text=overlap_content,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            symbol_name=f"{prev_element.name}_to_{curr_element.name}_overlap",
            symbol_type="overlap",
            metadata={
                "file_path": file_path,
                "symbol_name": f"{prev_element.name}_to_{curr_element.name}_overlap",
                "symbol_type": "overlap",
                "line_number": start_line,
                "overlaps_with": [prev_element.name, curr_element.name],
                "is_complete_element": False,
            },
        )
        return chunk

    def _get_element_hierarchy(self, element: CodeElement) -> dict[str, Any]:
        """Get the hierarchy information for an element."""
        hierarchy = {
            "name": element.name,
            "type": element.type,
            "parent": element.parent,
            "has_children": len(element.children) > 0,
            "children_count": len(element.children),
            "children_types": list(set(child.type for child in element.children))
            if element.children
            else [],
        }
        return hierarchy


class ChunkGenerator:
    """Main interface for generating smart chunks from code files."""

    def __init__(self, max_chunk_size: int = 512, overlap_size: int = 50, min_chunk_size: int = 50):
        self.structure_analyzer = CodeStructureAnalyzer()
        self.chunker = SmartChunker(max_chunk_size, overlap_size, min_chunk_size)

    def generate_chunks(
        self, file_path: Path, symbols: list[Symbol], file_content: str
    ) -> list[Chunk]:
        """
        Generate smart chunks from a file using structural analysis.
        """
        logger.debug(f"Generating chunks for {file_path} using smart chunking")

        # Analyze the structure of the code
        elements = self.structure_analyzer.analyze(file_path, symbols, file_content)

        # Create chunks based on the structural analysis
        chunks = self.chunker.create_chunks(elements, str(file_path))

        logger.debug(f"Generated {len(chunks)} chunks for {file_path}")
        return chunks

    async def generate_chunks_async(
        self, file_path: Path, symbols: list[Symbol], file_content: str
    ) -> list[Chunk]:
        """Async version of generate_chunks."""
        return self.generate_chunks(file_path, symbols, file_content)
