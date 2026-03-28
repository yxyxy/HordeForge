from __future__ import annotations

from pathlib import Path


def test_repo_store_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HORDEFORGE_HOME", str(tmp_path))

    from cli.repo_store import add_or_update_repo, get_repo_profile, set_secret_value

    set_secret_value("github.main", "token-123")
    add_or_update_repo(
        repo_id="yxyxy/HordeForge",
        repo_url="https://github.com/yxyxy/HordeForge",
        token_ref="github.main",
        set_default=True,
    )

    profile = get_repo_profile("yxyxy/HordeForge")
    assert profile is not None
    assert profile["repo_url"] == "https://github.com/yxyxy/HordeForge"
    assert profile["token_ref"] == "github.main"
    assert profile["repo_id"] == "yxyxy/HordeForge"


def test_repo_store_returns_default_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HORDEFORGE_HOME", str(tmp_path))

    from cli.repo_store import add_or_update_repo, get_repo_profile

    add_or_update_repo(
        repo_id="yxyxy/HordeForge",
        repo_url="https://github.com/yxyxy/HordeForge",
        token_ref=None,
        set_default=True,
    )

    default_profile = get_repo_profile(None)
    assert default_profile is not None
    assert default_profile["repo_id"] == "yxyxy/HordeForge"


def test_llm_profile_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HORDEFORGE_HOME", str(tmp_path))

    from cli.repo_store import add_or_update_llm_profile, get_llm_profile

    add_or_update_llm_profile(
        profile_name="openai-main",
        provider="openai",
        model="gpt-4o",
        base_url=None,
        api_key_ref="llm.openai",
        set_default=True,
    )

    profile = get_llm_profile("openai-main")
    assert profile is not None
    assert profile["profile_name"] == "openai-main"
    assert profile["provider"] == "openai"
    assert profile["model"] == "gpt-4o"
    assert profile["api_key_ref"] == "llm.openai"

    default_profile = get_llm_profile(None)
    assert default_profile is not None
    assert default_profile["profile_name"] == "openai-main"
