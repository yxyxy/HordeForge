import os

from fastapi.testclient import TestClient

os.environ["HORDEFORGE_STORAGE_BACKEND"] = "json"
os.environ["HORDEFORGE_QUEUE_BACKEND"] = "memory"

import scheduler.gateway as gateway
from scheduler.gateway import STATE


def test_health_postgres_endpoint_reports_status():
    client = TestClient(gateway.app)
    response = client.get("/health/postgres")
    assert response.status_code == 200
    body = response.json()
    if STATE.storage_backend_requested != "postgres":
        assert body["status"] in {"not_configured", "unavailable", "healthy"}
    else:
        assert body["status"] in {"healthy", "unhealthy"}
    assert "backend" in body


def test_health_redis_endpoint_reports_status():
    client = TestClient(gateway.app)
    response = client.get("/health/redis")
    assert response.status_code == 200
    body = response.json()
    if STATE.queue_backend_requested != "redis":
        assert body["status"] in {"not_configured", "unavailable", "healthy"}
    else:
        assert body["status"] in {"healthy", "unhealthy", "no_health_check"}
    assert "backend" in body
