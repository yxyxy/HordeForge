"""
Shared data models for RAG components.
Contains definitions for Symbol and Chunk that are used across multiple modules.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Symbol:
    """Represents a code symbol (class, function, method) extracted from code."""

    name: str
    type: str  # 'class', 'function', 'method'
    file_path: str
    line_number: int
    docstring: str | None = None
    parameters: list[str] = None
    decorators: list[str] = None
    class_name: str | None = None  # For methods, indicates the parent class
    return_annotation: str | None = None
    is_async: bool = False
    code_content: str = ""  # The actual code of the symbol

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.decorators is None:
            self.decorators = []


@dataclass
class Chunk:
    """Represents a text chunk with metadata for vector storage."""

    id: str
    text: str
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str = ""
    symbol_type: str = ""
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
