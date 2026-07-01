from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("addon", reason="addon package not installed")

from addon.runtime.python.horde_provider.gateway_client import (
    HORDE_GATEWAY_CLIENT_ID,
    HORDE_GATEWAY_CLIENT_MODE,
    HORDE_GATEWAY_CLIENT_PLATFORM,
    load_local_gateway_auth_context,
)


def _write_gateway_state(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".openclaw"
    identity_dir = state_dir / "identity"
    devices_dir = state_dir / "devices"
    identity_dir.mkdir(parents=True)
    devices_dir.mkdir(parents=True)
    (identity_dir / "device.json").write_text(
        json.dumps(
            {
                "version": 1,
                "deviceId": "device-123",
                "publicKeyPem": "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----\n",
                "privateKeyPem": "-----BEGIN PRIVATE KEY-----\nXYZ\n-----END PRIVATE KEY-----\n",
                "createdAtMs": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (identity_dir / "device-auth.json").write_text(
        json.dumps(
            {
                "version": 1,
                "deviceId": "device-123",
                "tokens": {
                    "operator": {
                        "token": "device-token-1",
                        "role": "operator",
                        "scopes": ["operator.admin"],
                        "updatedAtMs": 2,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (devices_dir / "paired.json").write_text(
        json.dumps(
            {
                "device-123": {
                    "deviceId": "device-123",
                    "publicKey": "raw-public-key",
                    "platform": "linux",
                    "clientId": "gateway-client",
                    "clientMode": "ui",
                    "role": "operator",
                    "approvedScopes": ["operator.admin"],
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return state_dir


def test_load_local_gateway_auth_context_prefers_paired_device_metadata(tmp_path: Path):
    state_dir = _write_gateway_state(tmp_path)

    context = load_local_gateway_auth_context(state_dir=state_dir)

    assert context.device_id == "device-123"
    assert context.token == "device-token-1"
    assert context.client_id == "gateway-client"
    assert context.client_mode == "ui"
    assert context.platform == "linux"
    assert context.scopes == ("operator.admin",)


def test_load_local_gateway_auth_context_falls_back_to_horde_defaults_without_pair_record(
    tmp_path: Path,
):
    state_dir = _write_gateway_state(tmp_path)
    (state_dir / "devices" / "paired.json").write_text("{}\n", encoding="utf-8")

    context = load_local_gateway_auth_context(state_dir=state_dir)

    assert context.client_id == HORDE_GATEWAY_CLIENT_ID
    assert context.client_mode == HORDE_GATEWAY_CLIENT_MODE
    assert context.platform == HORDE_GATEWAY_CLIENT_PLATFORM


def test_local_gateway_auth_context_rejects_missing_operator_token(tmp_path: Path):
    state_dir = _write_gateway_state(tmp_path)
    (state_dir / "identity" / "device-auth.json").write_text(
        json.dumps({"version": 1, "deviceId": "device-123", "tokens": {}}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="operator device token"):
        load_local_gateway_auth_context(state_dir=state_dir)
