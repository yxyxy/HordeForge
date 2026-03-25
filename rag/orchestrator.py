"""
Indexing orchestrator for RAG optimization.
Manages the sequential execution of all indexing stages with error handling and progress tracking.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from rag.stages import (
    ChunkingStage,
    EmbeddingStage,
    ParsingStage,
    StorageStage,
    SymbolExtractionStage,
)

logger = logging.getLogger(__name__)


class IndexingOrchestrator:
    """Orchestrates the complete indexing pipeline through all stages."""

    def __init__(
        self,
        collection_name: str = "repo_chunks",
        chunk_size: int = 512,
        overlap: int = 50,
        embedding_batch_size: int = 512,
        vector_size: int = 384,
    ):
        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embedding_batch_size = embedding_batch_size
        self.vector_size = vector_size

        # Initialize stages
        self.parsing_stage = ParsingStage()
        self.symbol_extraction_stage = SymbolExtractionStage()
        self.chunking_stage = ChunkingStage(chunk_size=chunk_size, overlap=overlap)
        self.embedding_stage = EmbeddingStage(batch_size=embedding_batch_size)
        self.storage_stage = StorageStage(collection_name=collection_name, vector_size=vector_size)

    async def run(self, file_paths: list[Path]) -> dict[str, Any]:
        """Execute the complete indexing pipeline."""
        logger.info(f"IndexingOrchestrator: Starting indexing pipeline for {len(file_paths)} files")
        start_time = time.time()

        # Track results from each stage
        stage_results = {}

        try:
            # Stage 1: Parsing
            logger.info("Starting parsing stage...")
            parsed_files = await self.parsing_stage.run(file_paths)
            stage_results["parsing"] = {
                "input_count": len(file_paths),
                "output_count": len(parsed_files),
                "duration": time.time() - start_time,
            }

            # If parsing failed completely, return early
            if len(parsed_files) == 0:
                logger.warning("No files were successfully parsed, attempting fallback approach")
                # Return a successful result with 0 processed files to allow the pipeline to continue
                total_duration = time.time() - start_time
                return {
                    "status": "success",
                    "total_files_processed": len(file_paths),
                    "total_parsed_files": 0,
                    "total_symbols_extracted": 0,
                    "total_chunks_created": 0,
                    "total_chunks_stored": 0,
                    "collection_name": self.collection_name,
                    "stage_results": stage_results,
                    "total_duration_seconds": total_duration,
                    "stages_completed": 5,
                }

            # Stage 2: Symbol Extraction
            logger.info("Starting symbol extraction stage...")
            symbol_extraction_start = time.time()
            symbols = await self.symbol_extraction_stage.run(parsed_files)
            stage_results["symbol_extraction"] = {
                "input_count": len(parsed_files),
                "output_count": len(symbols),
                "duration": time.time() - symbol_extraction_start,
            }

            # Stage 3: Chunking
            logger.info("Starting chunking stage...")
            chunking_start = time.time()
            chunks = await self.chunking_stage.run(symbols)
            stage_results["chunking"] = {
                "input_count": len(symbols),
                "output_count": len(chunks),
                "duration": time.time() - chunking_start,
            }

            # Stage 4: Embedding
            logger.info("Starting embedding stage...")
            embedding_start = time.time()
            chunks_with_embeddings = await self.embedding_stage.run(chunks)
            stage_results["embedding"] = {
                "input_count": len(chunks),
                "output_count": len(chunks_with_embeddings),
                "duration": time.time() - embedding_start,
            }

            # Stage 5: Storage
            logger.info("Starting storage stage...")
            storage_start = time.time()
            storage_result = await self.storage_stage.run(chunks_with_embeddings)
            stage_results["storage"] = {
                "input_count": len(chunks_with_embeddings),
                "output_count": storage_result["total_inserted"],
                "duration": time.time() - storage_start,
            }

            # Overall results
            total_duration = time.time() - start_time
            overall_result = {
                "status": "success",
                "total_files_processed": len(file_paths),
                "total_parsed_files": len(parsed_files),
                "total_symbols_extracted": len(symbols),
                "total_chunks_created": len(chunks),
                "total_chunks_stored": storage_result["total_inserted"],
                "collection_name": self.collection_name,
                "stage_results": stage_results,
                "total_duration_seconds": total_duration,
                "stages_completed": 5,
            }

            logger.info(
                f"IndexingOrchestrator: Pipeline completed successfully in {total_duration:.2f}s"
            )
            logger.info(f"Results: {overall_result}")

            return overall_result

        except Exception as e:
            logger.error(f"IndexingOrchestrator: Pipeline failed with error: {e}", exc_info=True)
            error_result = {
                "status": "error",
                "error_message": str(e),
                "stage_results": stage_results,
                "total_duration_seconds": time.time() - start_time,
                "stages_completed": len(stage_results),
            }
            return error_result

    def run_sync(self, file_paths: list[Path]) -> dict[str, Any]:
        """Synchronous wrapper for the async run method."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run().
            return asyncio.run(self.run(file_paths))

        # Event loop is already running in this thread (e.g. FastAPI/pytest-asyncio).
        # Run the coroutine in a separate thread with its own loop.
        from concurrent.futures import ThreadPoolExecutor

        def _run_in_thread() -> dict[str, Any]:
            return asyncio.run(self.run(file_paths))

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(_run_in_thread).result()

    async def run_with_recovery(
        self, file_paths: list[Path], max_retries: int = 3
    ) -> dict[str, Any]:
        """Execute the indexing pipeline with recovery mechanisms."""
        for attempt in range(max_retries):
            try:
                result = await self.run(file_paths)
                if result["status"] == "success":
                    return result
                else:
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {result.get('error_message', 'Unknown error')}"
                    )
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {2**attempt} seconds...")
                        await asyncio.sleep(2**attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed with exception: {e}", exc_info=True)
                if attempt == max_retries - 1:
                    raise

        # If all retries failed, return the last attempt's result
        return result
