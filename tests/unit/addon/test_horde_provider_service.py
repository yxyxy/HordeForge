from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

pytest.importorskip("addon", reason="addon package not installed")

from addon.runtime.python.horde_provider.service import HordeProviderService
from addon.runtime.python.horde_provider.store import HordeProviderProfileStore


def _oauth_json(
    *,
    access_token: str = "old-access",
    refresh_token: str = "refresh-token",
    expiry_date: int = 1,
    resource_url: str = "portal.qwen.ai",
) -> str:
    return json.dumps(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "refresh_token": refresh_token,
            "resource_url": resource_url,
            "expiry_date": expiry_date,
        }
    )


def test_service_resolves_runtime_auth_for_valid_token(tmp_path: Path):
    openclaw_agent_dir = tmp_path / "openclaw-agent"
    store = HordeProviderProfileStore(root_dir=tmp_path, openclaw_agent_dir=openclaw_agent_dir)
    store.import_qwen_oauth_profile(
        profile_id="team:valid",
        oauth_credentials_json=_oauth_json(expiry_date=9999999999999),
    )
    service = HordeProviderService(store=store)

    resolved = service.resolve_runtime_auth(profile_id="team:valid")

    assert resolved.provider_id == "horde-provider"
    assert resolved.model_ref == "horde-provider/qwen3-coder-plus"
    assert resolved.api_key == "old-access"
    assert resolved.base_url == "https://portal.qwen.ai/v1"
    assert resolved.default_headers["X-DashScope-AuthType"] == "qwen-oauth"
    auth_store = json.loads((openclaw_agent_dir / "auth-profiles.json").read_text(encoding="utf-8"))
    assert auth_store["profiles"]["horde-provider:team:valid"]["access"] == "old-access"


def test_service_refreshes_expired_token_and_uses_persisted_runtime_storage(
    monkeypatch, tmp_path: Path
):
    class _FakeResponse:
        status_code = 200
        text = '{"access_token":"new-access","token_type":"Bearer","expires_in":3600}'
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 3600,
            }

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _FakeResponse())
    openclaw_agent_dir = tmp_path / "openclaw-agent"
    store = HordeProviderProfileStore(root_dir=tmp_path, openclaw_agent_dir=openclaw_agent_dir)
    profile = store.import_qwen_oauth_profile(
        profile_id="team:expired",
        oauth_credentials_json=_oauth_json(expiry_date=1),
    )
    service = HordeProviderService(store=store)

    resolved = service.resolve_runtime_auth(profile_id="team:expired")

    assert resolved.api_key == "new-access"
    persisted_files = list(Path(profile.runtime_storage_dir).glob("*.oauth_creds.json"))
    assert persisted_files
    auth_store = json.loads((openclaw_agent_dir / "auth-profiles.json").read_text(encoding="utf-8"))
    assert auth_store["profiles"]["horde-provider:team:expired"]["access"] == "new-access"


def test_service_rejects_unknown_model_for_profile(tmp_path: Path):
    store = HordeProviderProfileStore(
        root_dir=tmp_path,
        openclaw_agent_dir=tmp_path / "openclaw-agent",
    )
    store.import_qwen_oauth_profile(
        profile_id="team:model",
        oauth_credentials_json=_oauth_json(expiry_date=9999999999999),
        available_models=["qwen3-coder-plus"],
    )
    service = HordeProviderService(store=store)

    with pytest.raises(ValueError, match="not allowed"):
        service.resolve_runtime_auth(profile_id="team:model", model="qwen3-coder-next")
