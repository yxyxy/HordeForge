from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from agents.qwen_oauth_token_manager import QwenOAuthTokenManager


def _creds_json(
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


def test_manager_returns_cached_credentials_when_token_is_valid(tmp_path: Path):
    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=9999999999999),
        storage_dir=tmp_path,
    )

    creds = manager.get_valid_credentials()

    assert creds["access_token"] == "old-access"
    assert creds["refresh_token"] == "refresh-token"


def test_manager_refreshes_and_persists_credentials(monkeypatch, tmp_path: Path):
    class _FakeResponse:
        status_code = 200
        text = '{"access_token":"new-access","token_type":"Bearer","expires_in":3600}'
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                # refresh_token intentionally omitted: manager must keep previous one
            }

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _FakeResponse())

    persisted: dict[str, str] = {}

    def _fake_set_secret_value(name: str, value: str):
        persisted[name] = value

    monkeypatch.setattr("cli.repo_store.set_secret_value", _fake_set_secret_value)

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1),
        credentials_secret_ref="llm.qwen-code.api_key",
        storage_dir=tmp_path,
    )

    creds = manager.get_valid_credentials()

    assert creds["access_token"] == "new-access"
    assert creds["refresh_token"] == "refresh-token"
    assert "llm.qwen-code.api_key" in persisted
    persisted_json = json.loads(persisted["llm.qwen-code.api_key"])
    assert persisted_json["access_token"] == "new-access"
    assert persisted_json["refresh_token"] == "refresh-token"


def test_manager_raises_on_non_json_refresh_response(monkeypatch, tmp_path: Path):
    class _FakeResponse:
        status_code = 200
        text = "<html>error</html>"
        headers = {"Content-Type": "text/html"}

        def json(self):
            raise requests.exceptions.JSONDecodeError("Expecting value", "", 0)

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _FakeResponse())

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1, refresh_token="refresh-token-non-json"),
        storage_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="non-JSON"):
        manager.get_valid_credentials()
