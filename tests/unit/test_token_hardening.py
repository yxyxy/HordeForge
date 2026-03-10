from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import scheduler.gateway as gateway
from agents.github_client import GitHubClient
from scheduler.gateway import (
    ARTIFACT_REPOSITORY,
    IDEMPOTENCY_STORE,
    RUN_REPOSITORY,
    RUN_RUNTIME_INPUTS,
    RUNS,
    STEP_LOG_REPOSITORY,
    app,
)


@pytest.fixture(autouse=True)
def _clean_gateway_storage():
    RUNS.clear()
    RUN_RUNTIME_INPUTS.clear()
    RUN_REPOSITORY.store.write_all([])
    STEP_LOG_REPOSITORY.store.write_all([])
    ARTIFACT_REPOSITORY.store.write_all([])
    IDEMPOTENCY_STORE.clear()
    gateway.CRON_DISPATCHER = None
    yield


def test_run_pipeline_sanitizes_sensitive_data_in_result_and_artifacts(monkeypatch):
    client = TestClient(app)

    def _fake_run(_pipeline_name, _inputs, *, run_id: str, metadata=None, **_kwargs):
        return {
            "run_id": run_id,
            "pipeline_name": "init_pipeline",
            "status": "SUCCESS",
            "summary": {"total_retries": 0, "step_durations_seconds": {}},
            "steps": {
                "repo_connector": {
                    "status": "SUCCESS",
                    "artifacts": [
                        {
                            "type": "repository_metadata",
                            "content": {
                                "github_token": "ghp_secret_token_12345678901234567890",
                                "note": "Authorization: Bearer abc.def.ghi",
                            },
                        }
                    ],
                    "decisions": [],
                    "logs": [
                        "Used token ghp_secret_token_12345678901234567890",
                        "Auth: Bearer abc.def.ghi",
                    ],
                    "next_actions": [],
                }
            },
            "run_state": {
                "run_id": run_id,
                "pipeline_name": "init_pipeline",
                "steps": [{"name": "repo_connector", "attempts": 1}],
                "current_step_index": 1,
                "run_status": "SUCCESS",
            },
            "trace": {
                "correlation_id": (metadata or {}).get("correlation_id"),
                "trace_id": "trace-id",
                "root_span_id": "root-span-id",
                "steps": [],
            },
        }

    monkeypatch.setattr("scheduler.gateway.engine.run", _fake_run)

    response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/acme/hordeforge.git",
                "github_token": "ghp_secret_token",
            },
            "source": "test",
            "correlation_id": "corr-token-hardening-1",
            "idempotency_key": "token-hardening-key-1",
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]

    persisted = RUN_REPOSITORY.get(run_id)
    assert persisted is not None
    persisted_json = json.dumps(persisted.to_dict())
    assert "ghp_secret_token" not in persisted_json
    assert "Bearer abc.def.ghi" not in persisted_json
    assert "[REDACTED]" in persisted_json

    artifacts = ARTIFACT_REPOSITORY.list_by_run(run_id)
    assert artifacts
    artifact_json = json.dumps([item.to_dict() for item in artifacts])
    assert "ghp_secret_token" not in artifact_json
    assert "Bearer abc.def.ghi" not in artifact_json
    assert "[REDACTED]" in artifact_json


def test_github_client_rejects_empty_token():
    try:
        GitHubClient(token="   ", repo="acme/hordeforge")
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty GitHub token")
