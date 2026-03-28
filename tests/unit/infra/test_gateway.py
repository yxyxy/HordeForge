import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ["HORDEFORGE_STORAGE_BACKEND"] = "json"
os.environ["HORDEFORGE_QUEUE_BACKEND"] = "memory"

import scheduler.gateway as gateway
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


@pytest.fixture(autouse=True)
def _clean_gateway_storage():
    RUNS.clear()
    RUN_REPOSITORY.store.write_all([])
    STEP_LOG_REPOSITORY.store.write_all([])
    ARTIFACT_REPOSITORY.store.write_all([])
    IDEMPOTENCY_STORE.clear()
    RUN_RUNTIME_INPUTS.clear()
    TASK_QUEUE.clear()
    gateway.CRON_DISPATCHER = None
    gateway.TENANT_REGISTRY = TenantRepositoryRegistry(
        mapping={
            "default": ("*",),
            "acme": ("acme/hordeforge",),
            "beta": ("beta/hordeforge",),
        },
        default_tenant_id="default",
        enforce_boundaries=True,
    )
    yield


def _operator_headers(
    *,
    key: str = "local-operator-key",
    role: str = "operator",
    source: str = "api",
) -> dict[str, str]:
    return {
        "X-Operator-Key": key,
        "X-Operator-Role": role,
        "X-Command-Source": source,
    }


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_run_pipeline_with_unknown_pipeline_returns_404():
    client = TestClient(app)
    response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "missing_pipeline",
            "inputs": {},
            "source": "test",
            "correlation_id": "test-correlation",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "PIPELINE_NOT_FOUND"
    assert body["error"]["message"].startswith("Pipeline file not found:")


def test_run_pipeline_request_model_validation():
    client = TestClient(app)
    response = client.post("/run-pipeline", json={"inputs": {}, "source": "test"})
    assert response.status_code == 422


def test_get_unknown_run_returns_error_envelope():
    client = TestClient(app)
    response = client.get("/runs/missing-run-id")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RUN_NOT_FOUND"


def test_get_run_supports_tenant_filter():
    client = TestClient(app)
    response_run = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
                "repository_full_name": "acme/hordeforge",
            },
            "source": "test",
            "correlation_id": "corr-tenant-get-1",
            "idempotency_key": "tenant-get-1",
            "tenant_id": "acme",
        },
    )
    run_id = response_run.json()["run_id"]

    ok = client.get(f"/runs/{run_id}", params={"tenant_id": "acme"})
    missing = client.get(f"/runs/{run_id}", params={"tenant_id": "beta"})

    assert ok.status_code == 200
    assert ok.json()["tenant_id"] == "acme"
    assert missing.status_code == 404


def test_get_run_returns_step_summary_and_trace():
    client = TestClient(app)
    response_run = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-status-1",
            "idempotency_key": "status-key-1",
        },
    )
    run_id = response_run.json()["run_id"]

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["step_summary"]["step_count"] >= 1
    assert "status_counts" in body["step_summary"]
    assert body["result"]["trace"]["correlation_id"] == "corr-status-1"
    assert body["result"]["trace"]["trace_id"]


def test_run_pipeline_suppresses_duplicate_idempotency_key():
    client = TestClient(app)
    request_payload = {
        "pipeline_name": "init_pipeline",
        "inputs": {"repo_url": "https://github.com/yxyxy/hordeforge.git", "github_token": "token"},
        "source": "test",
        "correlation_id": "corr-dup-1",
        "idempotency_key": "dup-key-1",
    }

    first = client.post("/run-pipeline", json=request_payload)
    second = client.post("/run-pipeline", json=request_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "started"
    assert second.json()["status"] == "duplicate"
    assert first.json()["run_id"] == second.json()["run_id"]


def test_run_pipeline_async_enqueues_task_and_queue_drain_executes_it():
    client = TestClient(app)
    queued = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
                "repository_full_name": "acme/hordeforge",
            },
            "source": "test",
            "correlation_id": "corr-queue-api-1",
            "idempotency_key": "queue-api-key-1",
            "async_mode": True,
            "tenant_id": "acme",
        },
    )

    assert queued.status_code == 200
    queued_body = queued.json()
    assert queued_body["status"] == "queued"
    task_id = queued_body["task_id"]

    queued_task = client.get(f"/queue/tasks/{task_id}")
    assert queued_task.status_code == 200
    queued_payload = queued_task.json()
    assert queued_payload["status"] == "QUEUED"
    assert queued_payload["tenant_id"] == "acme"
    assert queued_payload["repository_full_name"] == "acme/hordeforge"

    drained = client.post("/queue/drain", json={"max_items": 5}, headers=_operator_headers())
    assert drained.status_code == 200
    assert drained.json()["processed_count"] == 1

    completed_task = client.get(f"/queue/tasks/{task_id}")
    assert completed_task.status_code == 200
    completed_body = completed_task.json()
    assert completed_body["status"] == "SUCCEEDED"
    assert completed_body["result"]["status"] in {"started", "duplicate"}


def test_queue_drain_requires_permissions():
    client = TestClient(app)
    client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-queue-api-2",
            "idempotency_key": "queue-api-key-2",
            "async_mode": True,
        },
    )

    denied = client.post("/queue/drain", json={"max_items": 1})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_run_pipeline_logs_duplicate_suppression(caplog):
    client = TestClient(app)
    request_payload = {
        "pipeline_name": "init_pipeline",
        "inputs": {"repo_url": "https://github.com/yxyxy/hordeforge.git", "github_token": "token"},
        "source": "test",
        "correlation_id": "corr-dup-log-1",
        "idempotency_key": "dup-key-log-1",
    }

    with caplog.at_level("INFO", logger="hordeforge.gateway"):
        first = client.post("/run-pipeline", json=request_payload)
        second = client.post("/run-pipeline", json=request_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert any("idempotency_duplicate_suppressed" in record.message for record in caplog.records)


def test_cron_jobs_endpoint_lists_registered_jobs():
    client = TestClient(app)

    response = client.get("/cron/jobs")

    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "issue_scanner" in names
    assert "ci_monitor" in names


def test_cron_manual_trigger_runs_issue_scanner_and_publishes_trigger():
    client = TestClient(app)
    response = client.post(
        "/cron/jobs/issue_scanner/trigger",
        json={"payload": {"issues": [{"id": 303, "labels": [{"name": "agent:ready"}]}]}},
        headers=_operator_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "triggered"
    assert body["record"]["status"] == "SUCCESS"
    assert body["record"]["result"]["trigger_count"] == 1
    assert body["record"]["result"]["published_count"] == 1
    assert (
        body["record"]["result"]["published_triggers"][0]["pipeline_name"]
        == "backlog_analysis_pipeline"
    )


def test_cron_run_due_endpoint_runs_due_jobs_once_per_interval():
    client = TestClient(app)

    first = client.post("/cron/run-due", headers=_operator_headers())
    second = client.post("/cron/run-due", headers=_operator_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["triggered_count"] >= 2
    assert second.json()["triggered_count"] == 0


def test_cron_trigger_unknown_job_returns_404():
    client = TestClient(app)

    response = client.post(
        "/cron/jobs/missing-job/trigger",
        json={"payload": {}},
        headers=_operator_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CRON_JOB_NOT_FOUND"


def test_list_runs_supports_filters_and_pagination():
    client = TestClient(app)
    response_run = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-list-1",
            "idempotency_key": "list-key-1",
        },
    )
    assert response_run.status_code == 200

    response = client.get(
        "/runs", params={"pipeline_name": "init_pipeline", "limit": 5, "offset": 0}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert body["items"][0]["pipeline_name"] == "init_pipeline"


def test_list_runs_filters_by_tenant_id():
    client = TestClient(app)
    acme = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
                "repository_full_name": "acme/hordeforge",
            },
            "source": "test",
            "correlation_id": "corr-tenant-1",
            "idempotency_key": "tenant-key-1",
            "tenant_id": "acme",
        },
    )
    beta = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/beta/hordeforge.git",
                "github_token": "token",
                "repository_full_name": "beta/hordeforge",
            },
            "source": "test",
            "correlation_id": "corr-tenant-2",
            "idempotency_key": "tenant-key-2",
            "tenant_id": "beta",
        },
    )

    assert acme.status_code == 200
    assert beta.status_code == 200

    filtered = client.get("/runs", params={"tenant_id": "acme", "limit": 10, "offset": 0})
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert items
    assert all(item["tenant_id"] == "acme" for item in items)


def test_list_runs_filters_by_status_and_date_range():
    client = TestClient(app)
    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=1)).isoformat()
    date_to = (now + timedelta(days=1)).isoformat()

    ok_run = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-filter-ok",
            "idempotency_key": "filter-ok-1",
        },
    )
    fail_run = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "missing_pipeline_for_filter",
            "inputs": {},
            "source": "test",
            "correlation_id": "corr-filter-fail",
            "idempotency_key": "filter-fail-1",
        },
    )

    assert ok_run.status_code == 200
    assert fail_run.status_code == 404

    pipeline_response = client.get(
        "/runs",
        params={
            "pipeline_name": "init_pipeline",
            "date_from": date_from,
            "date_to": date_to,
            "offset": 0,
            "limit": 50,
        },
    )
    failed_response = client.get(
        "/runs",
        params={
            "status": "FAILED",
            "date_from": date_from,
            "date_to": date_to,
            "offset": 0,
            "limit": 50,
        },
    )

    assert pipeline_response.status_code == 200
    assert failed_response.status_code == 200
    pipeline_items = pipeline_response.json()["items"]
    failed_items = failed_response.json()["items"]
    assert any(item["run_id"] == ok_run.json()["run_id"] for item in pipeline_items)
    assert any(item["run_id"] == fail_run.json()["error"]["run_id"] for item in failed_items)


def test_list_runs_supports_offset_limit_and_run_id_filter():
    client = TestClient(app)
    run_ids: list[str] = []
    for index in range(3):
        response = client.post(
            "/run-pipeline",
            json={
                "pipeline_name": "init_pipeline",
                "inputs": {
                    "repo_url": "https://github.com/yxyxy/hordeforge.git",
                    "github_token": "token",
                },
                "source": "test",
                "correlation_id": f"corr-page-{index}",
                "idempotency_key": f"page-key-{index}",
            },
        )
        assert response.status_code == 200
        run_ids.append(response.json()["run_id"])

    paged = client.get("/runs", params={"offset": 1, "limit": 1})
    assert paged.status_code == 200
    assert paged.json()["count"] == 1

    exact = client.get("/runs", params={"run_id": run_ids[-1], "offset": 0, "limit": 10})
    assert exact.status_code == 200
    assert exact.json()["count"] == 1
    assert exact.json()["items"][0]["run_id"] == run_ids[-1]


def test_metrics_endpoint_exposes_runtime_metrics():
    client = TestClient(app)
    client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-metrics-1",
            "idempotency_key": "metrics-key-1",
        },
    )
    client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "missing_pipeline_for_metrics",
            "inputs": {},
            "source": "test",
            "correlation_id": "corr-metrics-2",
            "idempotency_key": "metrics-key-2",
        },
    )

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "hordeforge_runs_started_total" in body
    assert "hordeforge_runs_succeeded_total" in body
    assert "hordeforge_runs_failed_total" in body
    assert "hordeforge_step_duration_seconds_sum" in body
    assert "hordeforge_step_duration_seconds_count" in body
    assert "hordeforge_step_retries_total" in body


def test_cron_manual_endpoints_require_permissions():
    client = TestClient(app)

    run_due = client.post("/cron/run-due")
    trigger = client.post("/cron/jobs/issue_scanner/trigger", json={"payload": {}})

    assert run_due.status_code == 403
    assert trigger.status_code == 403
    assert run_due.json()["error"]["code"] == "FORBIDDEN"
    assert trigger.json()["error"]["code"] == "FORBIDDEN"


def test_override_endpoint_requires_role_and_source_headers():
    client = TestClient(app)
    run_response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-override-perm-1",
            "idempotency_key": "override-perm-key-1",
        },
    )
    run_id = run_response.json()["run_id"]

    response = client.post(
        f"/runs/{run_id}/override",
        json={"action": "explain", "reason": "check"},
        headers={"X-Operator-Key": "local-operator-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_override_retry_rejects_success_run():
    client = TestClient(app)
    run_response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-override-retry-1",
            "idempotency_key": "override-retry-key-1",
        },
    )
    run_id = run_response.json()["run_id"]

    # Force the run status to SUCCESS to test the override logic
    # (actual run may have failed due to git clone issues in test environment)
    record = RUN_REPOSITORY.get(run_id)
    if record:
        record.status = "SUCCESS"
        RUN_REPOSITORY.upsert(record)

    response = client.post(
        f"/runs/{run_id}/override",
        json={"action": "retry", "reason": "re-run"},
        headers=_operator_headers(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_OVERRIDE_STATE"


def test_override_stop_rejects_non_running_run():
    client = TestClient(app)
    run_response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-override-stop-1",
            "idempotency_key": "override-stop-key-1",
        },
    )
    run_id = run_response.json()["run_id"]

    response = client.post(
        f"/runs/{run_id}/override",
        json={"action": "stop", "reason": "stop finished run"},
        headers=_operator_headers(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_OVERRIDE_STATE"


def test_override_resume_replays_same_run_id_without_creating_new_run():
    client = TestClient(app)
    run_response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-override-resume-1",
            "idempotency_key": "override-resume-key-1",
        },
    )
    run_id = run_response.json()["run_id"]

    record = RUN_REPOSITORY.get(run_id)
    assert record is not None
    assert isinstance(record.result, dict)
    run_state = record.result.get("run_state")
    assert isinstance(run_state, dict)
    run_state["current_step_index"] = 1
    run_state["run_status"] = "BLOCKED"
    record.status = "BLOCKED"
    record.override_state = "STOPPED"
    RUN_REPOSITORY.upsert(record)
    RUN_RUNTIME_INPUTS[run_id] = {
        "repo_url": "https://github.com/yxyxy/hordeforge.git",
        "github_token": "token",
    }

    response = client.post(
        f"/runs/{run_id}/override",
        json={"action": "resume", "reason": "continue from blocked point"},
        headers=_operator_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["action"] == "resume"
    assert "trigger" not in body
    records = RUN_REPOSITORY.list(run_id=run_id, limit=10)
    assert len(records) == 1


def test_override_denied_request_is_audited(caplog):
    client = TestClient(app)
    run_response = client.post(
        "/run-pipeline",
        json={
            "pipeline_name": "init_pipeline",
            "inputs": {
                "repo_url": "https://github.com/yxyxy/hordeforge.git",
                "github_token": "token",
            },
            "source": "test",
            "correlation_id": "corr-override-audit-1",
            "idempotency_key": "override-audit-key-1",
        },
    )
    run_id = run_response.json()["run_id"]

    with caplog.at_level("INFO", logger="hordeforge.gateway"):
        response = client.post(
            f"/runs/{run_id}/override",
            json={"action": "explain", "reason": "denied"},
            headers={"X-Operator-Key": "wrong-key"},
        )

    assert response.status_code == 403
    assert any("manual_command_audit" in record.message for record in caplog.records)
