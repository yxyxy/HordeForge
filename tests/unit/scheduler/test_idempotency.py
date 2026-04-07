from __future__ import annotations

from scheduler.idempotency import IdempotencyStore, build_idempotency_key


def test_build_idempotency_key_is_stable_for_same_payload():
    payload = {"issue": {"id": 1, "title": "A"}}

    key_1 = build_idempotency_key(
        source="webhook",
        pipeline_name="feature_pipeline",
        payload=payload,
    )
    key_2 = build_idempotency_key(
        source="webhook",
        pipeline_name="feature_pipeline",
        payload=payload,
    )

    assert key_1 == key_2
    assert key_1.startswith("hf:")


def test_idempotency_store_remembers_and_returns_entry():
    store = IdempotencyStore(ttl_seconds=60)
    store.remember("k1", "run-1", {"status": "SUCCESS"})
    cached = store.get("k1")

    assert cached is not None
    assert cached["run_id"] == "run-1"
    assert cached["result"]["status"] == "SUCCESS"


def test_idempotency_store_clear_removes_cached_entries():
    store = IdempotencyStore(ttl_seconds=60)
    store.remember("k1", "run-1", {"status": "SUCCESS"})

    store.clear()

    assert store.get("k1") is None


def test_build_payload_hash_is_stable_for_same_payload_content():
    from scheduler.idempotency import build_payload_hash

    payload = {"a": 1, "b": {"x": 2}}
    assert build_payload_hash(payload) == build_payload_hash({"b": {"x": 2}, "a": 1})
