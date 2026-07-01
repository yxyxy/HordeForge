from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("addon", reason="addon package not installed")

from addon.runtime.python.horde_provider import __main__ as cli_main


def _oauth_payload() -> str:
    return json.dumps(
        {
            "access_token": "access-token",
            "token_type": "Bearer",
            "refresh_token": "refresh-token",
            "resource_url": "portal.qwen.ai",
            "expiry_date": 1776118155487,
        }
    )


def test_import_qwen_home_reads_default_oauth_creds(monkeypatch, tmp_path: Path, capsys):
    qwen_home = tmp_path / ".qwen"
    qwen_home.mkdir(parents=True)
    (qwen_home / "oauth_creds.json").write_text(_oauth_payload(), encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    exit_code = cli_main.main(
        [
            "import-qwen-home",
            "--profile-id",
            "name1",
            "--root-dir",
            str(tmp_path / "provider-root"),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "name1" in captured


def test_list_profiles_prints_registered_profile(monkeypatch, tmp_path: Path, capsys):
    root_dir = tmp_path / "provider-root"
    cli_main.main(
        [
            "import-json",
            "--profile-id",
            "name1",
            "--oauth-creds-json",
            _oauth_payload(),
            "--root-dir",
            str(root_dir),
        ]
    )

    exit_code = cli_main.main(["list-profiles", "--root-dir", str(root_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "name1" in output
    assert "qwen3-coder-plus" in output


def test_remove_profile_deletes_registered_profile(tmp_path: Path, capsys):
    root_dir = tmp_path / "provider-root"
    cli_main.main(
        [
            "import-json",
            "--profile-id",
            "name1",
            "--oauth-creds-json",
            _oauth_payload(),
            "--root-dir",
            str(root_dir),
        ]
    )

    exit_code = cli_main.main(
        ["remove-profile", "--profile-id", "name1", "--root-dir", str(root_dir)]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Removed horde-provider profile: name1" in output
