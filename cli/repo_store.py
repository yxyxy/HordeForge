from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _hordeforge_home() -> Path:
    custom_home = os.getenv("HORDEFORGE_HOME", "").strip()
    if custom_home:
        return Path(custom_home).expanduser()
    return Path("~/.hordeforge").expanduser()


def _config_path() -> Path:
    return _hordeforge_home() / "config.json"


def _secrets_path() -> Path:
    return _hordeforge_home() / "secrets.json"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort permissions tightening, especially relevant on Unix systems.
        pass


def _load_config_payload() -> dict[str, Any]:
    payload = _load_json_file(_config_path())
    repos = payload.get("repos")
    if not isinstance(repos, dict):
        repos = {}
    llm_profiles = payload.get("llm_profiles")
    if not isinstance(llm_profiles, dict):
        llm_profiles = {}
    default_repo = payload.get("default_repo")
    if default_repo is not None and not isinstance(default_repo, str):
        default_repo = None
    default_llm_profile = payload.get("default_llm_profile")
    if default_llm_profile is not None and not isinstance(default_llm_profile, str):
        default_llm_profile = None
    return {
        "repos": repos,
        "default_repo": default_repo,
        "llm_profiles": llm_profiles,
        "default_llm_profile": default_llm_profile,
    }


def _save_config_payload(payload: dict[str, Any]) -> None:
    _write_json_file(_config_path(), payload)


def _load_secrets_payload() -> dict[str, str]:
    payload = _load_json_file(_secrets_path())
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, str):
            normalized[key] = value
    return normalized


def _save_secrets_payload(payload: dict[str, str]) -> None:
    _write_json_file(_secrets_path(), payload)


def build_repo_token_ref(repo_id: str) -> str:
    return f"repo.{repo_id.strip().replace('/', '_')}.github_token"


def add_or_update_repo(
    repo_id: str, repo_url: str, token_ref: str | None = None, set_default: bool = False
) -> None:
    normalized_repo_id = repo_id.strip()
    payload = _load_config_payload()
    repos = payload["repos"]
    repos[normalized_repo_id] = {
        "repo_url": repo_url.strip(),
        "token_ref": token_ref.strip()
        if isinstance(token_ref, str) and token_ref.strip()
        else None,
    }
    if set_default or payload.get("default_repo") is None:
        payload["default_repo"] = normalized_repo_id
    _save_config_payload(payload)


def list_repo_profiles() -> list[dict[str, Any]]:
    payload = _load_config_payload()
    repos = payload.get("repos", {})
    default_repo = payload.get("default_repo")
    result: list[dict[str, Any]] = []
    for repo_id in sorted(repos.keys()):
        record = repos.get(repo_id, {})
        if not isinstance(record, dict):
            continue
        result.append(
            {
                "repo_id": repo_id,
                "repo_url": record.get("repo_url"),
                "token_ref": record.get("token_ref"),
                "is_default": repo_id == default_repo,
            }
        )
    return result


def get_repo_profile(repo_id: str | None) -> dict[str, Any] | None:
    payload = _load_config_payload()
    repos = payload.get("repos", {})
    target_repo_id = repo_id.strip() if isinstance(repo_id, str) and repo_id.strip() else None
    if target_repo_id is None:
        default_repo = payload.get("default_repo")
        if isinstance(default_repo, str) and default_repo in repos:
            target_repo_id = default_repo
    if target_repo_id is None or target_repo_id not in repos:
        return None
    record = repos[target_repo_id]
    if not isinstance(record, dict):
        return None
    return {
        "repo_id": target_repo_id,
        "repo_url": record.get("repo_url"),
        "token_ref": record.get("token_ref"),
    }


def set_default_repo(repo_id: str) -> bool:
    payload = _load_config_payload()
    normalized_repo_id = repo_id.strip()
    repos = payload.get("repos", {})
    if normalized_repo_id not in repos:
        return False
    payload["default_repo"] = normalized_repo_id
    _save_config_payload(payload)
    return True


def remove_repo(repo_id: str) -> str | None:
    payload = _load_config_payload()
    normalized_repo_id = repo_id.strip()
    repos = payload.get("repos", {})
    record = repos.pop(normalized_repo_id, None)
    if record is None:
        return None
    if payload.get("default_repo") == normalized_repo_id:
        payload["default_repo"] = None
    _save_config_payload(payload)
    if isinstance(record, dict):
        token_ref = record.get("token_ref")
        return token_ref if isinstance(token_ref, str) else None
    return None


def set_secret_value(key: str, value: str) -> None:
    payload = _load_secrets_payload()
    payload[key.strip()] = value
    _save_secrets_payload(payload)


def get_secret_value(key: str) -> str | None:
    payload = _load_secrets_payload()
    return payload.get(key.strip())


def list_secret_keys() -> list[str]:
    payload = _load_secrets_payload()
    return sorted(payload.keys())


def remove_secret_value(key: str) -> bool:
    payload = _load_secrets_payload()
    existed = key.strip() in payload
    payload.pop(key.strip(), None)
    _save_secrets_payload(payload)
    return existed


def build_llm_api_key_ref(profile_name: str) -> str:
    return f"llm.{profile_name.strip()}.api_key"


def add_or_update_llm_profile(
    profile_name: str,
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key_ref: str | None = None,
    set_default: bool = False,
) -> None:
    normalized_name = profile_name.strip()
    payload = _load_config_payload()
    llm_profiles = payload["llm_profiles"]
    llm_profiles[normalized_name] = {
        "provider": provider.strip(),
        "model": model.strip(),
        "base_url": base_url.strip() if isinstance(base_url, str) and base_url.strip() else None,
        "api_key_ref": (
            api_key_ref.strip() if isinstance(api_key_ref, str) and api_key_ref.strip() else None
        ),
    }
    if set_default or payload.get("default_llm_profile") is None:
        payload["default_llm_profile"] = normalized_name
    _save_config_payload(payload)


def list_llm_profiles() -> list[dict[str, Any]]:
    payload = _load_config_payload()
    llm_profiles = payload.get("llm_profiles", {})
    default_llm_profile = payload.get("default_llm_profile")
    result: list[dict[str, Any]] = []
    for profile_name in sorted(llm_profiles.keys()):
        record = llm_profiles.get(profile_name, {})
        if not isinstance(record, dict):
            continue
        result.append(
            {
                "profile_name": profile_name,
                "provider": record.get("provider"),
                "model": record.get("model"),
                "base_url": record.get("base_url"),
                "api_key_ref": record.get("api_key_ref"),
                "is_default": profile_name == default_llm_profile,
            }
        )
    return result


def get_llm_profile(profile_name: str | None) -> dict[str, Any] | None:
    payload = _load_config_payload()
    llm_profiles = payload.get("llm_profiles", {})
    target = (
        profile_name.strip() if isinstance(profile_name, str) and profile_name.strip() else None
    )
    if target is None:
        default_profile = payload.get("default_llm_profile")
        if isinstance(default_profile, str) and default_profile in llm_profiles:
            target = default_profile
    if target is None or target not in llm_profiles:
        return None
    record = llm_profiles[target]
    if not isinstance(record, dict):
        return None
    return {
        "profile_name": target,
        "provider": record.get("provider"),
        "model": record.get("model"),
        "base_url": record.get("base_url"),
        "api_key_ref": record.get("api_key_ref"),
    }


def set_default_llm_profile(profile_name: str) -> bool:
    payload = _load_config_payload()
    normalized_name = profile_name.strip()
    llm_profiles = payload.get("llm_profiles", {})
    if normalized_name not in llm_profiles:
        return False
    payload["default_llm_profile"] = normalized_name
    _save_config_payload(payload)
    return True


def remove_llm_profile(profile_name: str) -> str | None:
    payload = _load_config_payload()
    normalized_name = profile_name.strip()
    llm_profiles = payload.get("llm_profiles", {})
    record = llm_profiles.pop(normalized_name, None)
    if record is None:
        return None
    if payload.get("default_llm_profile") == normalized_name:
        payload["default_llm_profile"] = None
    _save_config_payload(payload)
    if isinstance(record, dict):
        api_key_ref = record.get("api_key_ref")
        return api_key_ref if isinstance(api_key_ref, str) else None
    return None
