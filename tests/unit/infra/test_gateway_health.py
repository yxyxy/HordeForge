import os

from fastapi.testclient import TestClient

os.environ["HORDEFORGE_STORAGE_BACKEND"] = "json"
os.environ["HORDEFORGE_QUEUE_BACKEND"] = "memory"

import scheduler.gateway as gateway


def test_health_postgres_endpoint_reports_status():
    client = TestClient(gateway.app)
    response = client.get("/health/postgres")
    assert response.status_code == 200
    body = response.json()
    if gateway.STORAGE_BACKEND_REQUESTED != "postgres":
        assert body["status"] == "not_configured"
        assert body["backend"] == gateway.STORAGE_BACKEND_REQUESTED
    else:
        assert body["status"] in {"healthy", "unhealthy"}


def test_health_redis_endpoint_reports_status():
    client = TestClient(gateway.app)
    response = client.get("/health/redis")
    assert response.status_code == 200
    body = response.json()
    if gateway.QUEUE_BACKEND_REQUESTED != "redis":
        assert body["status"] == "not_configured"
        assert body["backend"] == gateway.QUEUE_BACKEND_REQUESTED
    else:
        assert body["status"] in {"healthy", "unhealthy", "no_health_check"}
