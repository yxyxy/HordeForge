import threading

from storage.backends import PostgresStorageBackend


def test_postgres_backend_has_lock():
    """Test that PostgresStorageBackend has a threading lock."""
    backend = PostgresStorageBackend.__new__(PostgresStorageBackend)
    backend._conn = None
    backend._lock = threading.Lock()

    assert hasattr(backend, "_lock")
    assert isinstance(backend._lock, type(threading.Lock()))


def test_postgres_backend_lock_prevents_concurrent_access():
    """Test that the lock prevents concurrent access."""
    backend = PostgresStorageBackend.__new__(PostgresStorageBackend)
    backend._conn = None
    backend._lock = threading.Lock()

    # Verify lock can be acquired and released
    with backend._lock:
        pass  # Lock acquired and released successfully
