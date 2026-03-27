"""
Structured indexing stages for RAG optimization.
Implements the four main stages: parsing, symbol extraction, chunking, embedding, and storage.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import tree_sitter
from fastembed import TextEmbedding
from qdrant_client import models

from logging_config import get_logger
from rag.chunking import ChunkGenerator
from rag.config import get_embedding_model
from rag.models import Chunk, Symbol
from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor
from rag.tree_sitter_parser import get_language_for_file, parse_file
from rag.vector_store import QdrantStore

logger = get_logger(__name__)


@dataclass
class ParsedFile:
    """Represents a parsed file with its AST and metadata."""

    file_path: Path
    ast: tree_sitter.Tree
    language: str
    content: str


class ParsingStage:
    """Stage 1: Parse files using Tree-sitter to create AST representations."""

    def __init__(self):
        self.supported_extensions = {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".cxx",
            ".cc",
            ".c",
            ".h",
            ".cs",
        }

    async def run(self, file_paths: list[Path]) -> list[ParsedFile]:
        """Parse the provided files and return their AST representations."""
        logger.info(f"ParsingStage: Starting to parse {len(file_paths)} files")
        start_time = time.time()
        parsed_files = []

        for i, file_path in enumerate(file_paths):
            if file_path.suffix.lower() not in self.supported_extensions:
                logger.debug(f"Skipping unsupported file: {file_path}")
                continue

            logger.debug(f"Parsing file {i + 1}/{len(file_paths)}: {file_path}")

            try:
                # Read file content
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Parse the file using Tree-sitter
                ast = parse_file(file_path)
                if ast is None:
                    logger.warning(f"Failed to parse file: {file_path}")
                    continue

                # Get language for the file
                language = get_language_for_file(file_path)
                if not language:
                    logger.warning(f"Unknown language for file: {file_path}")
                    continue

                parsed_file = ParsedFile(
                    file_path=file_path, ast=ast, language=language, content=content
                )
                parsed_files.append(parsed_file)

            except Exception as e:
                logger.error(f"Error parsing file {file_path}: {e}")
                continue

        duration = time.time() - start_time
        logger.info(f"ParsingStage: Completed parsing {len(parsed_files)} files in {duration:.2f}s")
        return parsed_files


class SymbolExtractionStage:
    """Stage 2: Extract symbols (functions, classes, methods) from parsed files."""

    def __init__(self):
        self.extractor = TreeSitterSymbolExtractor()

    async def run(self, parsed_files: list[ParsedFile]) -> list[Symbol]:
        """Extract symbols from the parsed files."""
        logger.info(
            f"SymbolExtractionStage: Starting to extract symbols from {len(parsed_files)} parsed files"
        )
        start_time = time.time()
        all_symbols = []

        for i, parsed_file in enumerate(parsed_files):
            logger.debug(
                f"Extracting symbols from file {i + 1}/{len(parsed_files)}: {parsed_file.file_path}"
            )

            try:
                # Extract symbols using Tree-sitter
                file_symbols = self.extractor.extract_symbols(parsed_file.file_path)

                # If Tree-sitter extraction failed or returned no symbols, try fallback method
                if not file_symbols:
                    logger.info(
                        f"Tree-sitter extraction failed for {parsed_file.file_path}, trying fallback method"
                    )
                    # Use the old SymbolExtractor as fallback
                    from rag.symbol_extractor import SymbolExtractor

                    old_extractor = SymbolExtractor()
                    try:
                        file_symbols = old_extractor.extract_symbols(parsed_file.file_path)
                    except Exception as fallback_error:
                        logger.error(
                            f"Fallback extraction also failed for {parsed_file.file_path}: {fallback_error}"
                        )
                        continue

                # Enhance symbols with additional metadata
                for symbol in file_symbols:
                    # Find the actual code content for the symbol
                    code_content = self._get_symbol_code_content(
                        parsed_file.content, symbol.line_number
                    )
                    enhanced_symbol = Symbol(
                        name=symbol.name,
                        type=symbol.type,
                        file_path=str(parsed_file.file_path),
                        line_number=symbol.line_number,
                        docstring=symbol.docstring,
                        parameters=symbol.parameters,
                        decorators=symbol.decorators,
                        class_name=symbol.class_name,
                        return_annotation=symbol.return_annotation,
                        is_async=symbol.is_async,
                        code_content=code_content,
                    )
                    all_symbols.append(enhanced_symbol)

            except Exception as e:
                logger.error(f"Error extracting symbols from {parsed_file.file_path}: {e}")
                continue

        duration = time.time() - start_time
        logger.info(
            f"SymbolExtractionStage: Extracted {len(all_symbols)} symbols in {duration:.2f}s"
        )
        return all_symbols

    def _get_symbol_code_content(self, file_content: str, line_number: int) -> str:
        """Extract a reasonable amount of code around the symbol for context."""
        lines = file_content.splitlines()
        start_idx = max(0, line_number - 2)  # Start a bit before the symbol
        end_idx = min(
            len(lines), line_number + 10
        )  # End a bit after typical function/class definition

        # Expand to include more content if we have space
        while start_idx > 0 and lines[start_idx].strip() != "":
            start_idx -= 1

        while end_idx < len(lines) and lines[end_idx - 1].strip() != "":
            end_idx += 1

        # Limit to reasonable size to avoid huge chunks
        if end_idx - start_idx > 50:  # Max 50 lines
            end_idx = start_idx + 50

        return "\n".join(lines[start_idx:end_idx])


class ChunkingStage:
    """Stage 3: Split code into meaningful chunks based on symbols and structure."""

    def __init__(self, chunk_size: int = 512, overlap: int = 50, use_smart_chunking: bool = True):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.use_smart_chunking = use_smart_chunking
        if use_smart_chunking:
            self.chunk_generator = ChunkGenerator(max_chunk_size=chunk_size, overlap_size=overlap)

    async def run(self, symbols: list[Symbol]) -> list[Chunk]:
        """Create chunks from the extracted symbols."""
        logger.info(
            f"ChunkingStage: Starting to create chunks from {len(symbols)} symbols (smart_chunking: {self.use_smart_chunking})"
        )
        start_time = time.time()
        chunks = []

        # Track statistics for summary log
        total_structural_elements = 0
        total_files_processed = 0

        if self.use_smart_chunking:
            # Group symbols by file to process with smart chunking
            symbols_by_file = {}
            for symbol in symbols:
                if symbol.file_path not in symbols_by_file:
                    symbols_by_file[symbol.file_path] = []
                symbols_by_file[symbol.file_path].append(symbol)

            # Process each file separately with smart chunking
            for file_path_str, file_symbols in symbols_by_file.items():
                file_path = Path(file_path_str)
                total_files_processed += 1
                try:
                    # Read the file content to pass to the chunk generator
                    with open(file_path, encoding="utf-8") as f:
                        file_content = f.read()

                    # Generate chunks using the smart chunking approach
                    file_chunks = self.chunk_generator.generate_chunks(
                        file_path, file_symbols, file_content
                    )
                    chunks.extend(file_chunks)

                    # Count structural elements (this info comes from the chunking process)
                    # We'll estimate based on the number of symbols processed for this file
                    total_structural_elements += len(file_symbols)

                except FileNotFoundError:
                    logger.warning(
                        f"File not found during smart chunking: {file_path_str}, falling back to basic chunking"
                    )
                    # Fallback to basic chunking for this file
                    chunks.extend(await self._basic_chunking(file_symbols))
                except Exception as e:
                    logger.error(
                        f"Error during smart chunking for {file_path_str}: {e}, falling back to basic chunking"
                    )
                    # Fallback to basic chunking for this file
                    chunks.extend(await self._basic_chunking(file_symbols))
        else:
            # Use the original basic chunking approach
            chunks.extend(await self._basic_chunking(symbols))
            # For basic chunking, each symbol is treated as a structural element
            total_structural_elements = len(symbols)
            total_files_processed = len(set(symbol.file_path for symbol in symbols))

        duration = time.time() - start_time

        # Summary log in the requested format
        logger.info(
            f"Identified {total_structural_elements} structural elements, Generated {len(chunks)} chunks for {total_files_processed} files"
        )
        logger.info(f"ChunkingStage: Created {len(chunks)} chunks in {duration:.2f}s")
        return chunks

    async def _basic_chunking(self, symbols: list[Symbol]) -> list[Chunk]:
        """Original basic chunking approach for fallback or when smart chunking is disabled."""
        basic_chunks = []
        for i, symbol in enumerate(symbols):
            logger.debug(
                f"Creating chunks for symbol {i + 1}/{len(symbols)}: {symbol.name} in {symbol.file_path}"
            )

            try:
                # Create a chunk for each symbol
                chunk_id = str(uuid4())
                chunk = Chunk(
                    id=chunk_id,
                    text=symbol.code_content,
                    file_path=symbol.file_path,
                    start_line=symbol.line_number,
                    end_line=self._estimate_end_line(symbol.code_content, symbol.line_number),
                    symbol_name=symbol.name,
                    symbol_type=symbol.type,
                    metadata={
                        "file_path": symbol.file_path,
                        "symbol_name": symbol.name,
                        "symbol_type": symbol.type,
                        "line_number": symbol.line_number,
                        "docstring": symbol.docstring,
                        "parameters": symbol.parameters,
                        "class_name": symbol.class_name,
                        "is_async": symbol.is_async,
                    },
                )
                basic_chunks.append(chunk)

            except Exception as e:
                logger.error(
                    f"Error creating chunk for symbol {symbol.name} in {symbol.file_path}: {e}"
                )
                continue
        return basic_chunks

    def _estimate_end_line(self, code_content: str, start_line: int) -> int:
        """Estimate the end line of a code block."""
        lines = code_content.splitlines()
        return start_line + len(lines) - 1


class EmbeddingStage:
    """Stage 4: Compute embeddings for text chunks using batch processing."""

    def __init__(self, batch_size: int = 512, embedding_model: str = None):
        self.batch_size = batch_size
        self.embedding_model = embedding_model or get_embedding_model()
        self.embedder = TextEmbedding(model_name=self.embedding_model)

    async def run(self, chunks: list[Chunk]) -> list[Chunk]:
        """Compute embeddings for the text chunks."""
        logger.info(f"EmbeddingStage: Starting to compute embeddings for {len(chunks)} chunks")
        start_time = time.time()

        # Process chunks in batches for efficiency
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            logger.debug(
                f"Processing embedding batch {i // self.batch_size + 1}/{(len(chunks) - 1) // self.batch_size + 1}"
            )

            # Extract texts for this batch
            texts = [chunk.text for chunk in batch]

            # Compute embeddings for the batch
            try:
                embeddings = list(self.embedder.embed(texts))

                # Assign embeddings back to chunks
                for j, chunk in enumerate(batch):
                    chunk.metadata["embedding"] = embeddings[j].tolist()

            except Exception as e:
                logger.error(f"Error computing embeddings for batch: {e}")
                # Continue with the rest of the chunks even if this batch fails
                continue

        duration = time.time() - start_time
        logger.info(
            f"EmbeddingStage: Computed embeddings for {len(chunks)} chunks in {duration:.2f}s"
        )
        return chunks


class StorageStage:
    """Stage 5: Store chunks with embeddings in vector database."""

    def __init__(self, collection_name: str = "repo_chunks", vector_size: int = 384):
        self.collection_name = collection_name
        self.vector_size = vector_size
        # Use dynamic mode based on configuration to allow auto-fallback behavior
        # This preserves the intended auto mode functionality while fixing DNS resolution issues
        self.vector_store = QdrantStore(check_compatibility=False, mode=None)

    async def run(self, chunks: list[Chunk]) -> dict[str, Any]:
        """Store the chunks in the vector database."""
        logger.info(
            f"StorageStage: Starting to store {len(chunks)} chunks in collection '{self.collection_name}'"
        )
        start_time = time.time()

        # Create or update collection
        collection_exists = self.vector_store.collection_exists(self.collection_name)
        if not collection_exists:
            self.vector_store.create_collection(
                self.collection_name,
                vector_size=self.vector_size,
                distance=models.Distance.COSINE,
                indexing_threshold=500,
                hnsw_config={"m": 0},  # Optimize for fast ingestion
            )

        # Insert chunks using the vector store's buffer mechanism
        total_inserted = 0
        for chunk in chunks:
            try:
                point = {
                    "id": chunk.id,
                    "vector": chunk.metadata.get("embedding", []),
                    "payload": {
                        "text": chunk.text,
                        "file_path": chunk.file_path,
                        "symbol_name": chunk.symbol_name,
                        "symbol_type": chunk.symbol_type,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        **chunk.metadata,  # Include all other metadata
                    },
                }
                self.vector_store.add_point(self.collection_name, point)
                total_inserted += 1
            except Exception as e:
                logger.error(f"Error inserting chunk {chunk.id}: {e}")
                continue

        # Flush any remaining points in the buffer
        try:
            flushed = self.vector_store.close(self.collection_name)
            logger.info(f"Flushed remaining {flushed} points from buffer")
        except Exception as e:
            logger.error(f"Error flushing buffer: {e}")

        duration = time.time() - start_time
        logger.info(
            f"StorageStage: Stored {total_inserted}/{len(chunks)} chunks in {duration:.2f}s"
        )

        return {
            "total_chunks_processed": len(chunks),
            "total_inserted": total_inserted,
            "collection_name": self.collection_name,
            "duration_seconds": duration,
            "success_rate": total_inserted / len(chunks) if len(chunks) > 0 else 0,
        }
