from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("addon", reason="addon package not installed")

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


def test_store_imports_qwen_oauth_profile_and_persists_seed_credentials(tmp_path: Path):
    openclaw_agent_dir = tmp_path / "openclaw-agent"
    store = HordeProviderProfileStore(root_dir=tmp_path, openclaw_agent_dir=openclaw_agent_dir)

    profile = store.import_qwen_oauth_profile(
        profile_id="team:main",
        oauth_credentials_json=_oauth_json(expiry_date=9999999999999),
        default_model="qwen3-coder-plus",
    )

    assert profile.provider_id == "horde-provider"
    assert profile.profile_id == "team:main"
    assert profile.available_models == ["qwen3-coder-plus"]
    assert Path(profile.seed_credentials_file).exists()
    assert (
        json.loads(Path(profile.seed_credentials_file).read_text(encoding="utf-8"))["refresh_token"]
        == "refresh-token"
    )
    auth_store = json.loads((openclaw_agent_dir / "auth-profiles.json").read_text(encoding="utf-8"))
    assert auth_store["profiles"]["horde-provider:team:main"]["provider"] == "horde-provider"
    assert auth_store["profiles"]["horde-provider:team:main"]["refresh"] == "refresh-token"


def test_store_rejects_credentials_without_refresh_token(tmp_path: Path):
    store = HordeProviderProfileStore(
        root_dir=tmp_path,
        openclaw_agent_dir=tmp_path / "openclaw-agent",
    )

    with pytest.raises(ValueError, match="refresh_token"):
        store.import_qwen_oauth_profile(
            profile_id="team:broken",
            oauth_credentials_json=json.dumps({"access_token": "x"}),
        )


def test_store_imports_legacy_qwen_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "cli.repo_store.get_llm_profile",
        lambda profile_name: {
            "profile_name": profile_name,
            "provider": "qwen-code",
            "model": "qwen3-coder-plus",
            "api_key_ref": f"llm.{profile_name}.api_key",
        },
    )
    monkeypatch.setattr(
        "cli.repo_store.get_secret_value",
        lambda key: _oauth_json(refresh_token=f"{key}-refresh", expiry_date=9999999999999),
    )
    openclaw_agent_dir = tmp_path / "openclaw-agent"
    store = HordeProviderProfileStore(root_dir=tmp_path, openclaw_agent_dir=openclaw_agent_dir)

    profile = store.import_legacy_qwen_profile(
        legacy_profile_name="qwen-main",
        target_profile_id="migrated:main",
    )

    assert profile.profile_id == "migrated:main"
    assert profile.source == "legacy-repo-store"
    assert profile.legacy_profile_name == "qwen-main"
    assert profile.legacy_api_key_ref == "llm.qwen-main.api_key"
    auth_store = json.loads((openclaw_agent_dir / "auth-profiles.json").read_text(encoding="utf-8"))
    assert auth_store["profiles"]["horde-provider:migrated:main"]["provider"] == "horde-provider"


def test_store_removes_profile_and_auth_cache(tmp_path: Path):
    openclaw_agent_dir = tmp_path / "openclaw-agent"
    store = HordeProviderProfileStore(root_dir=tmp_path, openclaw_agent_dir=openclaw_agent_dir)
    profile = store.import_qwen_oauth_profile(
        profile_id="remove-me",
        oauth_credentials_json=_oauth_json(expiry_date=9999999999999),
        default_model="qwen3-coder-plus",
    )

    removed = store.remove_profile("remove-me")

    assert removed is True
    assert store.get_profile("remove-me") is None
    assert not Path(profile.seed_credentials_file).exists()
    auth_store = json.loads((openclaw_agent_dir / "auth-profiles.json").read_text(encoding="utf-8"))
    assert "horde-provider:remove-me" not in auth_store["profiles"]
