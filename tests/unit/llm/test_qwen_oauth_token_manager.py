from __future__ import annotations

import json
import os
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


def test_manager_removes_stale_lock_and_refreshes(monkeypatch, tmp_path: Path):
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

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1),
        storage_dir=tmp_path,
    )

    lock_path = tmp_path / f"{manager._key}.oauth_creds.lock"  # noqa: SLF001
    lock_path.write_text("12345", encoding="utf-8")
    old_timestamp = lock_path.stat().st_mtime - 3600
    os.utime(lock_path, (old_timestamp, old_timestamp))

    creds = manager.get_valid_credentials()

    assert creds["access_token"] == "new-access"


def test_lock_timeout_is_longer_than_refresh_http_timeout():
    assert QwenOAuthTokenManager._LOCK_TIMEOUT_MS >= 20_000


def test_manager_force_breaks_lock_after_timeout(monkeypatch, tmp_path: Path):
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

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1),
        storage_dir=tmp_path,
    )

    lock_path = tmp_path / f"{manager._key}.oauth_creds.lock"  # noqa: SLF001
    lock_path.write_text("another-process", encoding="utf-8")

    original_timeout = QwenOAuthTokenManager._LOCK_TIMEOUT_MS
    original_stale = QwenOAuthTokenManager._LOCK_STALE_MS
    try:
        QwenOAuthTokenManager._LOCK_TIMEOUT_MS = 50
        QwenOAuthTokenManager._LOCK_STALE_MS = 86_400_000
        creds = manager.get_valid_credentials()
    finally:
        QwenOAuthTokenManager._LOCK_TIMEOUT_MS = original_timeout
        QwenOAuthTokenManager._LOCK_STALE_MS = original_stale

    assert creds["access_token"] == "new-access"


def test_manager_refreshes_without_file_lock_when_lock_is_unavailable(monkeypatch, tmp_path: Path):
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

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1),
        storage_dir=tmp_path,
    )

    original_timeout = QwenOAuthTokenManager._LOCK_TIMEOUT_MS
    try:
        QwenOAuthTokenManager._LOCK_TIMEOUT_MS = 20
        monkeypatch.setattr(
            "agents.qwen_oauth_token_manager.os.open",
            lambda *a, **k: (_ for _ in ()).throw(FileExistsError()),
        )
        creds = manager.get_valid_credentials()
    finally:
        QwenOAuthTokenManager._LOCK_TIMEOUT_MS = original_timeout

    assert creds["access_token"] == "new-access"


def test_manager_returns_refreshed_credentials_when_local_persist_fails(
    monkeypatch, tmp_path: Path
):
    class _FakeResponse:
        status_code = 200
        text = (
            '{"access_token":"new-access","refresh_token":"new-refresh",'
            '"token_type":"Bearer","expires_in":3600}'
        )
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
            }

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _FakeResponse())

    manager = QwenOAuthTokenManager(
        oauth_credentials_json=_creds_json(expiry_date=1),
        storage_dir=tmp_path,
    )
    monkeypatch.setattr(
        manager,
        "_save_credentials",
        lambda _credentials: (_ for _ in ()).throw(PermissionError("no write access")),
    )

    creds = manager.get_valid_credentials()

    assert creds["access_token"] == "new-access"
