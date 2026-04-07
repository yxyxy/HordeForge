from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["HORDEFORGE_STORAGE_BACKEND"] = "json"
os.environ["HORDEFORGE_QUEUE_BACKEND"] = "memory"

import scheduler.gateway as gateway
from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor
from scheduler.gateway import (
    ARTIFACT_REPOSITORY,
    IDEMPOTENCY_STORE,
    RUN_REPOSITORY,
    RUN_RUNTIME_INPUTS,
    RUNS,
    STEP_LOG_REPOSITORY,
    TASK_QUEUE,
    app,
)
from scheduler.tenant_registry import TenantRepositoryRegistry


def _operator_headers() -> dict[str, str]:
    return {
        "X-Operator-Key": "local-operator-key",
        "X-Operator-Role": "operator",
        "X-Command-Source": "api",
    }


class _CountingSuccessAgent:
    def __init__(self, counters: dict[str, int], key: str) -> None:
        self._counters = counters
        self._key = key

    def run(self, _context):
        self._counters[self._key] += 1
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class _FlakyBlockAgent:
    def __init__(self, counters: dict[str, int], key: str) -> None:
        self._counters = counters
        self._key = key

    def run(self, _context):
        self._counters[self._key] += 1
        if self._counters[self._key] == 1:
            return {
                "status": "FAILED",
                "artifacts": [],
                "decisions": [],
                "logs": ["first run failure"],
                "next_actions": [],
            }
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def _clean_gateway_state() -> None:
    RUNS.clear()
    RUN_REPOSITORY.store.write_all([])
    STEP_LOG_REPOSITORY.store.write_all([])
    ARTIFACT_REPOSITORY.store.write_all([])
    IDEMPOTENCY_STORE.clear()
    RUN_RUNTIME_INPUTS.clear()
    TASK_QUEUE.clear()
    gateway.CRON_DISPATCHER = None
    gateway.TENANT_REGISTRY = TenantRepositoryRegistry(
        mapping={"default": ("*",)},
        default_tenant_id="default",
        enforce_boundaries=True,
    )


def test_gateway_resume_replays_only_pending_steps_with_same_hash(monkeypatch):
    _clean_gateway_state()

    pipeline_path = Path("tests/integration/_tmp_gateway_replay_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: gateway_replay_pipeline
steps:
  - name: step_a
    agent: counted_success
    on_failure: stop_pipeline
  - name: step_b
    agent: flaky_block
    on_failure: create_issue_for_human
""".strip(),
        encoding="utf-8",
    )

    counters = {"a": 0, "b": 0}

    def _agent_factory(agent_name: str):
        if agent_name == "counted_success":
            return _CountingSuccessAgent(counters, "a")
        if agent_name == "flaky_block":
            return _FlakyBlockAgent(counters, "b")
        raise RuntimeError(f"unknown agent: {agent_name}")

    test_engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )
    monkeypatch.setattr(gateway, "engine", test_engine)

    client = TestClient(app)

    try:
        first = client.post(
            "/run-pipeline",
            json={
                "pipeline_name": str(pipeline_path),
                "inputs": {},
                "source": "test",
                "correlation_id": "it-gateway-replay-1",
                "idempotency_key": "it-gateway-replay-key-1",
            },
        )
        assert first.status_code == 200
        run_id = first.json()["run_id"]

        record = RUN_REPOSITORY.get(run_id)
        assert record is not None
        assert record.status == "BLOCKED"
        assert counters == {"a": 1, "b": 1}

        resumed = client.post(
            f"/runs/{run_id}/override",
            json={"action": "resume", "reason": "continue"},
            headers=_operator_headers(),
        )
        assert resumed.status_code == 200

        final_record = RUN_REPOSITORY.get(run_id)
        assert final_record is not None
        assert final_record.status == "SUCCESS"
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert counters == {"a": 1, "b": 2}
