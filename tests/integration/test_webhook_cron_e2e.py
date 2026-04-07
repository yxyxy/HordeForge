from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as webhook_api
import scheduler.gateway as gateway
from agents.context_utils import build_agent_result
from api.security import compute_github_signature
from hordeforge_config import RunConfig
from scheduler.idempotency import IdempotencyStore
from storage.repositories.artifact_repository import ArtifactRepository
from storage.repositories.run_repository import RunRepository
from storage.repositories.step_log_repository import StepLogRepository

pytestmark = pytest.mark.usefixtures("stub_llm_for_pipeline_runtime")


def _operator_headers() -> dict[str, str]:
    return {
        "X-Operator-Key": "local-operator-key",
        "X-Operator-Role": "operator",
        "X-Command-Source": "api",
    }


def _signed_webhook_request(
    client: TestClient,
    *,
    event_type: str,
    payload: dict[str, object],
    delivery: str,
    secret: str,
):
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = compute_github_signature(secret, body)
    return client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event_type,
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": signature,
        },
    )


@pytest.fixture(autouse=True)
def _clean_runtime_state(monkeypatch):
    storage_dir = Path("tests/integration/_tmp_webhook_cron_storage")
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

    monkeypatch.setenv("HORDEFORGE_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setattr(webhook_api, "config", RunConfig.from_env())

    def _fast_rag_initializer_run(self, _context):
        return build_agent_result(
            status="SUCCESS",
            artifact_type="rag_index",
            artifact_content={
                "index_id": "it-fast-rag-index",
                "indexed_files_count": 1,
                "total_symbols_count": 1,
                "source_repo": "acme/hordeforge",
                "vector_store_status": False,
                "keyword_index_status": True,
                "collection_name": "repo_chunks",
                "rag_working": True,
                "reused_existing_index": True,
            },
            reason="Fast integration test stub for RAG initializer.",
            confidence=1.0,
            logs=["RAG initializer fast stub used in integration tests."],
            next_actions=["memory_agent"],
        )

    def _fast_test_runner_run(self, _context):
        return build_agent_result(
            status="SUCCESS",
            artifact_type="test_results",
            artifact_content={
                "exit_code": 0,
                "passed": 1,
                "failed": 0,
                "framework": "pytest",
                "summary": "Fast integration test stub.",
            },
            reason="Fast integration test stub for test runner.",
            confidence=1.0,
            logs=["Test runner fast stub used in integration tests."],
            next_actions=["review_agent"],
        )

    monkeypatch.setattr("agents.rag_initializer.RagInitializer.run", _fast_rag_initializer_run)
    monkeypatch.setattr("agents.test_runner.TestRunner.run", _fast_test_runner_run)

    yield
    shutil.rmtree(storage_dir, ignore_errors=True)


def test_webhook_issue_event_e2e_triggers_feature_pipeline_and_persists_run():
    webhook_client = TestClient(webhook_api.app)
    gateway_client = TestClient(gateway.app)
    payload = {
        "action": "opened",
        "issue": {"id": 501, "title": "E2E feature flow", "body": "Implement endpoint and tests"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    response = _signed_webhook_request(
        webhook_client,
        event_type="issues",
        payload=payload,
        delivery="hf-p2-025-delivery-1",
        secret="test-webhook-secret",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["pipeline_name"] == "feature_pipeline"
    run_id = body["trigger_result"]["run_id"]

    run_response = gateway_client.get(f"/runs/{run_id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["run_id"] == run_id
    assert run_payload["pipeline_name"] == "feature_pipeline"
    assert run_payload["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert run_payload["step_summary"]["step_count"] >= 1
    assert run_payload["result"]["summary"]["run_id"] == run_id


def test_webhook_workflow_failure_e2e_triggers_ci_scanner_pipeline():
    webhook_client = TestClient(webhook_api.app)
    gateway_client = TestClient(gateway.app)
    payload = {
        "workflow_run": {
            "id": 702,
            "status": "completed",
            "conclusion": "failure",
            "name": "ci",
            "failed_jobs": [{"name": "unit-tests"}],
        },
        "repository": {"full_name": "acme/hordeforge"},
        "issue": {"id": 7020, "title": "CI failed"},
    }

    response = _signed_webhook_request(
        webhook_client,
        event_type="workflow_run",
        payload=payload,
        delivery="hf-p2-026-delivery-1",
        secret="test-webhook-secret",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["pipeline_name"] == "ci_scanner_pipeline"
    run_id = body["trigger_result"]["run_id"]

    run_response = gateway_client.get(f"/runs/{run_id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["pipeline_name"] == "ci_scanner_pipeline"
    assert run_payload["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "BLOCKED"}
    assert run_payload["step_summary"]["step_count"] >= 1


def test_cron_jobs_e2e_cover_registered_jobs_and_idempotency():
    gateway_client = TestClient(gateway.app)

    jobs_response = gateway_client.get("/cron/jobs")
    assert jobs_response.status_code == 200
    names = {item["name"] for item in jobs_response.json()["items"]}
    assert "issue_scanner" in names
    assert "ci_monitor" in names

    issue_payload = {"issues": [{"id": 9001, "labels": [{"name": "agent:opened"}]}]}
    ci_payload = {
        "workflow_runs": [{"id": 9002, "status": "completed", "conclusion": "failure"}],
        "repository": {"full_name": "acme/hordeforge"},
    }

    first_issue = gateway_client.post(
        "/cron/jobs/issue_scanner/trigger",
        json={"payload": issue_payload},
        headers=_operator_headers(),
    )
    second_issue = gateway_client.post(
        "/cron/jobs/issue_scanner/trigger",
        json={"payload": issue_payload},
        headers=_operator_headers(),
    )
    first_ci = gateway_client.post(
        "/cron/jobs/ci_monitor/trigger",
        json={"payload": ci_payload},
        headers=_operator_headers(),
    )
    second_ci = gateway_client.post(
        "/cron/jobs/ci_monitor/trigger",
        json={"payload": ci_payload},
        headers=_operator_headers(),
    )

    assert first_issue.status_code == 200
    assert second_issue.status_code == 200
    assert first_ci.status_code == 200
    assert second_ci.status_code == 200

    first_issue_result = first_issue.json()["record"]["result"]
    second_issue_result = second_issue.json()["record"]["result"]
    first_ci_result = first_ci.json()["record"]["result"]
    second_ci_result = second_ci.json()["record"]["result"]

    assert first_issue_result["published_count"] == 1
    assert second_issue_result["published_count"] == 0
    assert first_ci_result["published_count"] == 1
    assert second_ci_result["published_count"] == 0

    scanner_runs = gateway.RUN_REPOSITORY.list(pipeline_name="issue_scanner_pipeline", limit=20)
    ci_scanner_runs = gateway.RUN_REPOSITORY.list(pipeline_name="ci_scanner_pipeline", limit=20)
    assert len(scanner_runs) == 1
    assert len(ci_scanner_runs) == 1
