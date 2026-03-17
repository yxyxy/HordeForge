"""
High-performance async ingestion pipeline for Qdrant.

Architecture:
[Reader] → [Batcher] → [Embedder (batched)] → [Async Queue]
                                                    ↓
                                          [Async Upsert Workers]
                                                    ↓
                                                Qdrant
"""

import asyncio
import logging
import time
from collections.abc import Iterator

from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import HnswConfigDiff

logger = logging.getLogger(__name__)

# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)


# ------------------------
# Utils
# ------------------------
def batch(iterable: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# ------------------------
# Pipeline
# ------------------------
class IngestionPipeline:
    def __init__(
        self,
        client: AsyncQdrantClient,
        embedder: TextEmbedding | None = None,
        batch_size: int = 1024,  # 🔥 было 256 → теперь 1024+
        num_workers: int = 8,  # 🔥 больше параллелизма
        queue_size: int = 50,
        max_inflight: int = 16,  # 🔥 ограничение параллельных запросов
    ):
        self.client = client
        self.embedder = embedder or TextEmbedding()

        self.batch_size = batch_size
        self.num_workers = num_workers
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)

        self.semaphore = asyncio.Semaphore(max_inflight)

        self._workers: list[asyncio.Task] = []

        self._total_indexed = 0
        self._total_flushed = 0

    # ------------------------
    # Collection Management
    # ------------------------
    async def prepare_collection(self, collection_name: str, vector_size: int = 384):
        """
        Prepare collection for fast ingestion by disabling HNSW index temporarily.

        Args:
            collection_name: Name of the collection to prepare
            vector_size: Size of the vectors to store
        """
        # Recreate collection with m=0 for faster ingestion
        await self.client.recreate_collection(
            collection_name=collection_name,
            vectors_config={"size": vector_size, "distance": "Cosine"},
            hnsw_config=HnswConfigDiff(m=0),  # Disable index during ingestion
        )
        logger.info(f"Prepared collection '{collection_name}' for fast ingestion (m=0)")

    async def optimize_collection(self, collection_name: str, m: int = 16):
        """
        Optimize collection after ingestion by enabling HNSW index.

        Args:
            collection_name: Name of the collection to optimize
            m: HNSW M parameter for indexing quality
        """
        await self.client.update_collection(
            collection_name=collection_name, hnsw_config=HnswConfigDiff(m=m)
        )
        logger.info(f"Optimized collection '{collection_name}' with m={m}")

    # ------------------------
    # Worker
    # ------------------------
    async def _upsert_worker(self, collection_name: str, worker_id: int):
        logger.debug(f"Worker {worker_id} started")

        while True:
            batch = await self.queue.get()

            if batch is None:
                self.queue.task_done()
                break

            try:
                async with self.semaphore:
                    await self.client.upsert(
                        collection_name=collection_name,
                        points=batch,
                        wait=False,  # 🔥 критично
                    )

                self._total_flushed += len(batch)

                # 🔥 редкий лог (не тормозит)
                if self._total_flushed % 5000 == 0:
                    logger.info(f"Indexed: {self._total_flushed}")

            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

            finally:
                self.queue.task_done()

        logger.debug(f"Worker {worker_id} stopped")

    # ------------------------
    async def _start_workers(self, collection_name: str):
        self._workers = [
            asyncio.create_task(self._upsert_worker(collection_name, i))
            for i in range(self.num_workers)
        ]
        logger.info(f"Started {self.num_workers} workers")

    async def _stop_workers(self):
        for _ in self._workers:
            await self.queue.put(None)

        await asyncio.gather(*self._workers, return_exceptions=True)

    # ------------------------
    # Embedding + batching
    # ------------------------
    async def _produce(self, texts: list[str]):
        for text_batch in batch(texts, self.batch_size):
            # 🔥 батчевый embed (ключевой буст)
            embeddings = list(self.embedder.embed(text_batch))

            points = [
                {
                    "id": self._total_indexed + i,
                    "vector": emb.tolist(),
                    "payload": {"text": text},
                }
                for i, (text, emb) in enumerate(zip(text_batch, embeddings, strict=False))
            ]

            self._total_indexed += len(points)

            await self.queue.put(points)

    # ------------------------
    async def run(self, texts: list[str], collection_name: str, vector_size: int = 384):
        start = time.time()

        # Prepare collection for fast ingestion
        await self.prepare_collection(collection_name, vector_size)

        await self._start_workers(collection_name)

        try:
            producer_task = asyncio.create_task(self._produce(texts))

            await producer_task
            await self.queue.join()

        finally:
            await self._stop_workers()

        # Optimize collection after ingestion
        await self.optimize_collection(collection_name)

        duration = time.time() - start
        rate = self._total_indexed / duration if duration else 0

        result = {
            "total_indexed": self._total_indexed,
            "total_flushed": self._total_flushed,
            "duration_seconds": round(duration, 2),
            "rate_per_second": round(rate, 2),
        }

        logger.info(f"Done: {self._total_indexed} points in {duration:.2f}s ({rate:.0f}/sec)")

        return result

    def run_sync(self, texts: list[str], collection_name: str, vector_size: int = 384):
        return asyncio.run(self.run(texts, collection_name, vector_size))
