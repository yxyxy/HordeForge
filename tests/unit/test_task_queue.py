from __future__ import annotations

import pytest

from scheduler.task_queue import ExternalBrokerQueueAdapter, InMemoryTaskQueue, QueueTaskRequest


def test_in_memory_task_queue_roundtrip_enqueue_claim_and_complete():
    queue = InMemoryTaskQueue()
    queued = queue.enqueue(
        QueueTaskRequest(
            pipeline_name="init_pipeline",
            inputs={"repo_url": "https://github.com/yxyxy/hordeforge.git"},
            source="test",
            correlation_id="corr-queue-1",
            idempotency_key="queue-key-1",
            tenant_id="Tenant-A",
            repository_full_name="Acme/Repo",
        )
    )

    claimed = queue.claim_next(max_items=5)
    assert len(claimed) == 1
    assert claimed[0].task_id == queued.task_id
    assert claimed[0].status == "RUNNING"
    assert claimed[0].tenant_id == "tenant-a"
    assert claimed[0].repository_full_name == "acme/repo"

    completed = queue.mark_succeeded(queued.task_id, {"status": "started", "run_id": "run-1"})
    assert completed.status == "SUCCEEDED"
    assert completed.result == {"status": "started", "run_id": "run-1"}


def test_external_broker_adapter_is_placeholder():
    adapter = ExternalBrokerQueueAdapter(broker_url="redis://localhost:6379/0")

    with pytest.raises(NotImplementedError):
        adapter.enqueue(
            QueueTaskRequest(
                pipeline_name="init_pipeline",
                inputs={},
                source="test",
                correlation_id="corr-queue-2",
                idempotency_key=None,
            )
        )
