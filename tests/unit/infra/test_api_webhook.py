from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.main as webhook_api
from api.security import compute_github_signature
from hordeforge_config import RunConfig
from scheduler.gateway import RUNS


@pytest.fixture(autouse=True)
def _stub_run_pipeline(monkeypatch):
    """Keep webhook tests focused on routing/signature/idempotency behavior."""
    seen_runs: dict[str, str] = {}
    counter = {"value": 0}

    def _fake_run_pipeline(request):
        idempotency_key = getattr(request, "idempotency_key", "") or ""
        pipeline_name = getattr(request, "pipeline_name", "unknown")

        if idempotency_key in seen_runs:
            run_id = seen_runs[idempotency_key]
            status = "duplicate"
        else:
            counter["value"] += 1
            run_id = f"run-{counter['value']}"
            seen_runs[idempotency_key] = run_id
            status = "started"

        return {
            "status": status,
            "pipeline": pipeline_name,
            "run_id": run_id,
            "result": {"summary": {"run_id": run_id}},
        }

    monkeypatch.setattr(webhook_api, "run_pipeline", _fake_run_pipeline)


def _set_test_secret(monkeypatch) -> str:
    monkeypatch.setenv("HORDEFORGE_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setattr(webhook_api, "config", RunConfig.from_env())
    return "test-webhook-secret"


def _signed_request(
    client: TestClient, *, event_type: str, payload: dict, secret: str, delivery: str
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


def test_webhook_rejects_invalid_signature(monkeypatch):
    secret = _set_test_secret(monkeypatch)
    client = TestClient(webhook_api.app)
    body = b'{"action":"opened"}'
    bad_signature = compute_github_signature("wrong-secret", body)

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": bad_signature,
        },
    )

    assert secret == "test-webhook-secret"
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook signature"


def test_webhook_routes_issue_event_to_feature_pipeline(monkeypatch):
    RUNS.clear()
    secret = _set_test_secret(monkeypatch)
    client = TestClient(webhook_api.app)
    payload = {
        "action": "opened",
        "issue": {"id": 11, "title": "Feature request", "body": "Implement X"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    response = _signed_request(
        client,
        event_type="issues",
        payload=payload,
        secret=secret,
        delivery="delivery-issues-1",
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "accepted"
    assert data["pipeline_name"] == "feature_pipeline"
    assert data["trigger_result"]["run_id"]
    assert data["trigger_result"]["result"]["summary"]["run_id"] == data["trigger_result"]["run_id"]


def test_webhook_routes_failed_workflow_run_to_ci_fix_pipeline(monkeypatch):
    RUNS.clear()
    secret = _set_test_secret(monkeypatch)
    client = TestClient(webhook_api.app)
    payload = {
        "workflow_run": {"id": 77, "status": "completed", "conclusion": "failure"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    response = _signed_request(
        client,
        event_type="workflow_run",
        payload=payload,
        secret=secret,
        delivery="delivery-workflow-1",
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "accepted"
    assert data["pipeline_name"] == "ci_fix_pipeline"
    assert data["trigger_result"]["pipeline"] == "ci_fix_pipeline"


def test_webhook_duplicate_delivery_is_suppressed_by_idempotency(monkeypatch):
    RUNS.clear()
    secret = _set_test_secret(monkeypatch)
    client = TestClient(webhook_api.app)
    payload = {
        "action": "opened",
        "issue": {"id": 901, "title": "Duplicate event check"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    first = _signed_request(
        client,
        event_type="issues",
        payload=payload,
        secret=secret,
        delivery="delivery-duplicate-1",
    )
    second = _signed_request(
        client,
        event_type="issues",
        payload=payload,
        secret=secret,
        delivery="delivery-duplicate-1",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["trigger_result"]["status"] == "started"
    assert second.json()["trigger_result"]["status"] == "duplicate"
    assert first.json()["trigger_result"]["run_id"] == second.json()["trigger_result"]["run_id"]


def test_webhook_ignores_unsupported_events(monkeypatch, caplog):
    RUNS.clear()
    secret = _set_test_secret(monkeypatch)
    client = TestClient(webhook_api.app)
    payload = {"zen": "keep it logically awesome"}

    with caplog.at_level("INFO", logger="hordeforge.webhook_api"):
        response = _signed_request(
            client,
            event_type="ping",
            payload=payload,
            secret=secret,
            delivery="delivery-ping-1",
        )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "ignored"
    assert data["reason"].startswith("unsupported_event_type")
    assert any("webhook_event_ignored" in record.message for record in caplog.records)
