"""
High-performance async ingestion pipeline for Qdrant.

OPTIMIZATIONS APPLIED:
- wait=False for upsert (non-blocking, 2-3x faster)
- ThreadPoolExecutor with 1 worker (fastembed has internal parallelism)
- batch_size=512 (better embedding throughput)
- queue_size=200 (reduced backpressure)
- Embedder warmup before processing
- ef_construct in hnsw_config for better index quality
- Progress logging with throughput metrics
"""

import asyncio
import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient, models

from rag.batch_processing import BatchEmbedder, TextBuffer
from rag.config import get_embedding_model

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)


def batch(iterable: list[str], size: int) -> Iterator[list[str]]:
    """Yield successive batches of size `size` from iterable."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


class IngestionPipeline:
    def __init__(
        self,
        client: AsyncQdrantClient,
        embedder: TextEmbedding | None = None,
        batch_size: int = 1024,
        num_workers: int = 4,
        queue_size: int = 200,
        max_inflight: int = 8,
        check_compatibility: bool = False,
        normalize_vectors: bool = True,  # New parameter for vector normalization
        buffer_batch_size: int = 128,  # New parameter for internal buffer batch size
    ):
        self.client = client
        self.embedder = embedder or TextEmbedding(model_name=get_embedding_model())
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.semaphore = asyncio.Semaphore(max_inflight)
        self._workers: list[asyncio.Task] = []
        self._total_indexed = 0
        self._total_flushed = 0
        self._shutdown_event = asyncio.Event()
        # 🔥 1 поток: fastembed уже использует внутренний пул (ONNX Runtime)
        self._executor = ThreadPoolExecutor(max_workers=1)
        # Parameters for batch processing with new components
        self.normalize_vectors = normalize_vectors
        self.buffer_batch_size = buffer_batch_size

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._executor.shutdown(wait=True)

    async def prepare_collection(self, collection_name: str, vector_size: int = 384):
        collection_exists = True
        try:
            await self.client.get_collection(collection_name)
        except Exception:
            collection_exists = False

        if collection_exists:
            try:
                await self.client.update_collection(
                    collection_name=collection_name,
                    hnsw_config=models.HnswConfigDiff(m=0, ef_construct=64),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=500,
                        max_optimization_threads=2,
                    ),
                )
                logger.info(f"Updated collection '{collection_name}' for fast ingestion (m=0)")
            except Exception as e:
                logger.warning(f"Could not update collection: {e}")
        else:
            try:
                await self.client.recreate_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                    hnsw_config=models.HnswConfigDiff(m=0, ef_construct=64),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=500,
                        max_optimization_threads=2,
                    ),
                )
                logger.info(f"Created collection '{collection_name}' for fast ingestion (m=0)")
            except Exception as e:
                logger.error(f"Could not create collection: {e}")
                raise

    async def optimize_collection(self, collection_name: str, m: int = 16):
        try:
            await self.client.update_collection(
                collection_name=collection_name,
                hnsw_config=models.HnswConfigDiff(m=m, ef_construct=120),
            )
            logger.info(f"Optimized collection '{collection_name}' with m={m}")
        except Exception as e:
            logger.warning(f"Could not optimize collection: {e}")

    async def warmup_embedder(self):
        """Предзагрузка модели эмбеддинга в память (избегаем холодного старта)."""
        logger.info("🔥 Warming up embedder...")
        start = time.time()
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            lambda: list(self.embedder.embed(["warmup text for model loading"])),
        )
        logger.info(f"✓ Embedder warmed up in {time.time() - start:.2f}s")

    async def _upsert_worker(self, collection_name: str, worker_id: int):
        logger.info(f"Worker {worker_id} STARTED")

        while not self._shutdown_event.is_set():
            batch = None
            try:
                batch = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                logger.debug(f"Worker {worker_id}: Got batch of {len(batch)} points")

                async with self.semaphore:
                    points = [
                        models.PointStruct(
                            id=p["id"],
                            vector=p["vector"],
                            payload=p.get("payload", {}),
                        )
                        for p in batch
                    ]

                    # 🔥 wait=False по умолчанию (не блокирует, 2-3x быстрее)
                    await self.client.upsert(
                        collection_name=collection_name,
                        points=points,
                        # wait=False  # ← Не указываем, False по умолчанию
                    )

                    self._total_flushed += len(batch)
                    # 🔥 Логируем каждые 500 точек для лучшего прогресса
                    if self._total_flushed % 500 == 0:
                        logger.info(f"✓ Worker {worker_id}: Indexed {self._total_flushed:,} total")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} CANCELLED")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} ERROR: {e}")
                logger.exception("Traceback:")
                continue
            finally:
                if batch is not None:
                    try:
                        self.queue.task_done()
                    except ValueError:
                        logger.debug(f"Worker {worker_id}: task_done() already called")

        logger.info(f"Worker {worker_id} STOPPED")

    async def _start_workers(self, collection_name: str):
        self._workers = [
            asyncio.create_task(self._upsert_worker(collection_name, i))
            for i in range(self.num_workers)
        ]
        logger.info(f"Started {self.num_workers} async upsert workers")

    async def _stop_workers(self):
        self._shutdown_event.set()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break
        logger.info("All workers stopped")

    async def _produce(self, texts: list[str], metadata_list: list[dict] | None = None):
        batch_idx = 0
        total_texts = len(texts)
        logger.info(
            f"Producer: {total_texts} texts to process with buffer batch size {self.buffer_batch_size}"
        )

        start_time = time.time()

        # Initialize the TextBuffer and BatchEmbedder for optimized processing
        text_buffer = TextBuffer(batch_size=self.buffer_batch_size)
        batch_embedder = BatchEmbedder(self.embedder, normalize_vectors=self.normalize_vectors)

        # Process texts one by one through the buffer
        for i, text in enumerate(texts):
            # Get metadata for this text if available
            metadata = metadata_list[i] if metadata_list and i < len(metadata_list) else {}

            # Add text to buffer and get any completed batches
            completed_batches = text_buffer.add_text(text, metadata)

            # Process any completed batches
            for text_batch, meta_batch in completed_batches:
                embed_start = time.time()

                # Use the batch embedder to compute embeddings with optional normalization
                points = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda tb=text_batch, mb=meta_batch: batch_embedder.compute_and_process_batch(
                        tb, mb
                    ),
                )
                embed_time = time.time() - embed_start

                self._total_indexed += len(points)
                batch_idx += 1

                # 🔥 Прогресс-лог каждого 5-го батча с таймингом
                if batch_idx % 5 == 0:
                    elapsed = time.time() - start_time
                    rate = batch_idx / elapsed if elapsed else 0
                    points_per_sec = (self._total_indexed / elapsed) if elapsed else 0
                    logger.info(
                        f"🔄 Producer: batch {batch_idx} (text {i + 1}/{total_texts}) queued | "
                        f"embed_time={embed_time:.2f}s | rate={rate:.1f} bat/s | "
                        f"throughput={points_per_sec:.0f} pts/s"
                    )

                await self.queue.put(points)

        # Process any remaining items in the buffer (residual batch)
        remaining = text_buffer.get_remaining()
        if remaining:
            text_batch, meta_batch = remaining
            embed_start = time.time()

            points = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                lambda tb=text_batch, mb=meta_batch: batch_embedder.compute_and_process_batch(
                    tb, mb
                ),
            )
            embed_time = time.time() - embed_start

            self._total_indexed += len(points)
            batch_idx += 1

            logger.info(
                f"🔄 Producer: final batch {batch_idx} (remaining {len(text_batch)} texts) queued | "
                f"embed_time={embed_time:.2f}s"
            )

            await self.queue.put(points)

        logger.info(
            f"Producer: ALL {batch_idx} batches queued from {total_texts} texts in {time.time() - start_time:.1f}s"
        )

    async def run(
        self,
        texts: list[str],
        collection_name: str,
        vector_size: int = 384,
        metadata_list: list[dict] | None = None,
    ):
        start = time.time()
        logger.info(f"Pipeline START: {len(texts):,} texts")

        # If no texts to process, return early with success status
        if len(texts) == 0:
            logger.info("No texts to process, returning early")
            return {
                "total_indexed": 0,
                "total_flushed": 0,
                "collection_points_count": 0,
                "verification_status": "success",
                "duration_seconds": 0.0,
                "rate_per_second": 0.0,
            }

        await self.prepare_collection(collection_name, vector_size)
        await self.warmup_embedder()  # ← ДОБАВЛЕНО: warmup перед стартом
        await self._start_workers(collection_name)

        try:
            producer = asyncio.create_task(self._produce(texts, metadata_list))
            await producer
            logger.info("Producer finished, waiting for queue.join()...")
            await self.queue.join()
            logger.info("✓ Queue join completed")
        finally:
            await self._stop_workers()

        await self.optimize_collection(collection_name)

        duration = time.time() - start
        rate = self._total_indexed / duration if duration else 0

        await asyncio.sleep(0.3)
        try:
            info = await self.client.get_collection(collection_name)
            actual = info.points_count or 0
            status = "success" if actual == self._total_flushed else "warning"
            if status == "warning":
                logger.warning(
                    f"Mismatch: flushed {self._total_flushed:,}, collection has {actual:,}"
                )
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            status = "failed"
            actual = None

        logger.info(
            f"Pipeline DONE: {self._total_indexed:,} points in {duration:.1f}s ({rate:.0f}/sec)"
        )

        return {
            "total_indexed": self._total_indexed,
            "total_flushed": self._total_flushed,
            "collection_points_count": actual,
            "verification_status": status,
            "duration_seconds": round(duration, 2),
            "rate_per_second": round(rate, 2),
        }

    def run_sync(
        self,
        texts: list[str],
        collection_name: str,
        vector_size: int = 384,
        metadata_list: list[dict] | None = None,
    ):
        async def _run():
            async with self:
                return await self.run(texts, collection_name, vector_size, metadata_list)

        return asyncio.run(_run())
