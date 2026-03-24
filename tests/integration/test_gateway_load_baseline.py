from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import pytest

import scheduler.gateway as gateway
from observability.benchmarking import BurstScenario, evaluate_burst_result
from scheduler.gateway import PipelineRequest, run_pipeline
from scheduler.idempotency import IdempotencyStore
from storage.repositories.artifact_repository import ArtifactRepository
from storage.repositories.run_repository import RunRepository
from storage.repositories.step_log_repository import StepLogRepository


@pytest.fixture(autouse=True)
def _clean_runtime_state(monkeypatch):
    storage_dir = Path("tests/integration/_tmp_load_storage")
    if storage_dir.exists():
        shutil.rmtree(storage_dir, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gateway, "RUN_REPOSITORY", RunRepository(storage_dir=str(storage_dir)))
    monkeypatch.setattr(
        gateway, "STEP_LOG_REPOSITORY", StepLogRepository(storage_dir=str(storage_dir))
    )
    monkeypatch.setattr(
        gateway, "ARTIFACT_REPOSITORY", ArtifactRepository(storage_dir=str(storage_dir))
    )
    monkeypatch.setattr(gateway, "IDEMPOTENCY_STORE", IdempotencyStore(ttl_seconds=3600))

    gateway.RUNS.clear()
    gateway.RUN_RUNTIME_INPUTS.clear()
    gateway.CRON_DISPATCHER = None
    yield
    shutil.rmtree(storage_dir, ignore_errors=True)


def _write_load_pipeline(path: Path) -> None:
    path.write_text(
        """
pipeline_name: load_baseline_pipeline
steps:
  - name: repo_connector
    agent: repo_connector
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )


def test_gateway_baseline_load_handles_50_parallel_triggers():
    pipeline_path = Path("tests/integration/_tmp_load_baseline_pipeline.yaml")
    _write_load_pipeline(pipeline_path)

    def _trigger(index: int) -> tuple[float, dict[str, object]]:
        start = perf_counter()
        payload = run_pipeline(
            PipelineRequest(
                pipeline_name=str(pipeline_path),
                inputs={
                    "repo_url": "https://github.com/yxyxy/hordeforge.git",
                    "github_token": f"token-{index}",
                },
                source="load_test",
                correlation_id=f"load-corr-{index}",
                idempotency_key=f"load-key-{index}",
            )
        )
        latency = perf_counter() - start
        if isinstance(payload, dict):
            return latency, payload
        return latency, {"status": "error"}

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(_trigger, range(50)))
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    latencies = sorted(item[0] for item in results)
    statuses = [str(item[1].get("status")) for item in results]
    started_count = sum(1 for status in statuses if status == "started")
    error_count = len(statuses) - started_count

    p50 = latencies[(len(latencies) // 2) - 1]
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    error_rate = error_count / len(results)

    assert len(results) == 50
    assert started_count == 50
    assert error_rate == 0.0
    assert p95 < 8.0
    assert p95 >= p50

    analysis = evaluate_burst_result(
        burst_size=50,
        started_count=started_count,
        p95_latency_seconds=p95,
        scenarios=[BurstScenario(burst_size=50, max_error_rate=0.01, max_p95_latency_seconds=8.0)],
    )
    assert analysis["saturation"] in {"green", "yellow"}
