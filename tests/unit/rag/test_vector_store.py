from __future__ import annotations

from rag.vector_store import QdrantStore


class _ScoredPoint:
    def __init__(self, *, point_id: str, score: float, payload: dict):
        self.id = point_id
        self.score = score
        self.payload = payload


class _QueryResult:
    def __init__(self, points: list[_ScoredPoint]):
        self.points = points


class _ClientWithQueryPointsOnly:
    def query_points(self, collection_name, query, limit, query_filter=None):
        assert collection_name == "repo_chunks"
        assert query
        assert limit == 3
        assert query_filter is None
        return _QueryResult(
            [
                _ScoredPoint(
                    point_id="p-1",
                    score=0.91,
                    payload={"file_path": "a.py", "text": "hello"},
                )
            ]
        )


class _CollectionInfo:
    def __init__(self, points_count: int):
        self.points_count = points_count


def test_qdrant_store_search_uses_query_points_when_search_not_available():
    store = QdrantStore.__new__(QdrantStore)
    store.client = _ClientWithQueryPointsOnly()
    store.collection_exists = lambda collection_name: collection_name == "repo_chunks"

    result = QdrantStore.search(
        store,
        collection_name="repo_chunks",
        query_vector=[0.1, 0.2, 0.3],
        limit=3,
    )

    assert len(result) == 1
    assert result[0]["id"] == "p-1"
    assert result[0]["score"] == 0.91
    assert result[0]["payload"]["file_path"] == "a.py"


def test_qdrant_store_collection_points_count_reads_collection_info():
    store = QdrantStore.__new__(QdrantStore)
    store.client = type(
        "_Client",
        (),
        {"get_collection": lambda self, name: _CollectionInfo(points_count=42)},
    )()

    assert store.get_collection_points_count("repo_chunks") == 42
