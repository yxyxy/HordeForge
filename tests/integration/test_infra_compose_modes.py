from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _load_compose() -> dict:
    with COMPOSE_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert isinstance(payload, dict)
    return payload


def test_gateway_boots_with_local_defaults():
    compose = _load_compose()
    services = compose["services"]
    gateway = services["gateway"]
    environment = gateway["environment"]

    assert environment["HORDEFORGE_STORAGE_BACKEND"] == "${HORDEFORGE_STORAGE_BACKEND:-json}"
    assert environment["HORDEFORGE_QUEUE_BACKEND"] == "${HORDEFORGE_QUEUE_BACKEND:-memory}"
    assert environment["HORDEFORGE_VECTOR_STORE_MODE"] == "${HORDEFORGE_VECTOR_STORE_MODE:-auto}"


def test_gateway_boots_with_team_defaults():
    compose = _load_compose()
    services = compose["services"]

    assert services["db"]["profiles"] == ["team"]
    assert services["redis"]["profiles"] == ["team"]
    assert services["qdrant"]["profiles"] == ["team"]
    assert services["qdrant-mcp"]["profiles"] == ["team"]


def test_gateway_handles_missing_qdrant_in_auto_mode():
    compose = _load_compose()
    gateway = compose["services"]["gateway"]
    environment = gateway["environment"]

    assert gateway["depends_on"] == []
    assert environment["HORDEFORGE_VECTOR_STORE_MODE"] == "${HORDEFORGE_VECTOR_STORE_MODE:-auto}"
