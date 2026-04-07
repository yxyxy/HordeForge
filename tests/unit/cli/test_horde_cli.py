from __future__ import annotations

import argparse
import json
import sys
from types import ModuleType, SimpleNamespace

import requests

from cli import horde_cli


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_run_task_interactive_submits_feature_pipeline(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        captured["source"] = source
        return {"status": "started", "run_id": "run-123"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    args = SimpleNamespace(act=True, plan=False, model="gpt-4o")

    exit_code = horde_cli.run_task_interactive("Implement authentication", args)

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "feature_pipeline"
    assert captured["source"] == "horde_task"
    assert captured["inputs"] == {
        "prompt": "Implement authentication",
        "mode": "act",
        "model": "gpt-4o",
    }


def test_show_history_reads_runs_from_gateway(monkeypatch, capsys):
    captured: dict[str, object] = {}

    def _fake_get(url: str, *, params: dict, timeout: float) -> _Response:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response(
            {
                "items": [
                    {
                        "run_id": "run-1",
                        "pipeline_name": "feature_pipeline",
                        "status": "SUCCESS",
                        "created_at": "2026-03-27T10:00:00Z",
                    }
                ]
            }
        )

    monkeypatch.setattr(horde_cli.requests, "get", _fake_get)

    exit_code = horde_cli.show_history(limit=5, page=2)
    output = capsys.readouterr().out

    assert exit_code == horde_cli.EXIT_OK
    assert captured["url"] == f"{horde_cli.CONFIG.gateway_url}/runs"
    assert captured["params"] == {"offset": 5, "limit": 5}
    assert "run-1 | feature_pipeline | SUCCESS" in output


def test_show_history_returns_error_on_request_failure(monkeypatch):
    def _fake_get(url: str, *, params: dict, timeout: float):
        raise requests.RequestException("gateway unavailable")

    monkeypatch.setattr(horde_cli.requests, "get", _fake_get)

    exit_code = horde_cli.show_history(limit=10, page=1)
    assert exit_code == horde_cli.EXIT_ERROR


def test_pipeline_run_init_alias_uses_init_pipeline(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-init"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)

    exit_code = horde_cli.run_pipeline(
        pipeline_name="init",
        inputs_str="{}",
        repo_url="https://github.com/example/repo",
        token="test-token",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "init_pipeline"
    assert captured["inputs"] == {
        "repo_url": "https://github.com/example/repo",
        "github_token": "test-token",
    }


def test_pipeline_run_init_resolves_repo_profile(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-init-profile"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(
        horde_cli,
        "get_repo_profile",
        lambda repo_id: {
            "repo_id": repo_id,
            "repo_url": "https://github.com/yxyxy/HordeForge",
            "token_ref": "github.main",
        },
    )
    monkeypatch.setattr(horde_cli, "_get_secret_value", lambda key: "stored-token")

    exit_code = horde_cli.run_pipeline(
        pipeline_name="init",
        inputs_str="{}",
        pipeline_target="yxyxy/HordeForge",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "init_pipeline"
    assert captured["inputs"] == {
        "repo_url": "https://github.com/yxyxy/HordeForge",
        "github_token": "stored-token",
    }


def test_pipeline_run_init_auto_saves_repo_profile(monkeypatch):
    captured: dict[str, object] = {}
    saved_repo: dict[str, object] = {}
    saved_secret: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-init-autosave"}

    def _fake_add_or_update_repo(
        repo_id: str, repo_url: str, token_ref: str | None = None, set_default: bool = False
    ) -> None:
        saved_repo.update(
            {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "token_ref": token_ref,
                "set_default": set_default,
            }
        )

    def _fake_gateway_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        saved_secret.update({"path": path, "payload": payload})
        return {"status": "ok"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(horde_cli, "get_repo_profile", lambda repo_id: None)
    monkeypatch.setattr(horde_cli, "add_or_update_repo", _fake_add_or_update_repo)
    monkeypatch.setattr(horde_cli, "_gateway_post", _fake_gateway_post)

    exit_code = horde_cli.run_pipeline(
        pipeline_name="init",
        inputs_str="{}",
        repo_url="https://github.com/OWNER/REPO",
        token="token-123",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "init_pipeline"
    assert saved_secret == {
        "path": "/secrets",
        "payload": {"name": "repo.OWNER_REPO.github_token", "value": "token-123"},
    }
    assert saved_repo == {
        "repo_id": "OWNER/REPO",
        "repo_url": "https://github.com/OWNER/REPO",
        "token_ref": "repo.OWNER_REPO.github_token",
        "set_default": False,
    }


def test_pipeline_run_ci_fix_uses_default_repo_and_ci_defaults(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-ci-defaults"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(
        horde_cli,
        "get_repo_profile",
        lambda repo_id: {
            "repo_id": "OWNER/REPO",
            "repo_url": "https://github.com/OWNER/REPO",
            "token_ref": None,
        },
    )
    monkeypatch.setattr(horde_cli, "_resolve_local_head_sha", lambda: "abcdef123456")

    exit_code = horde_cli.run_pipeline(
        pipeline_name="ci_scanner_pipeline",
        inputs_str="{}",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "ci_scanner_pipeline"
    assert captured["inputs"] == {
        "repository": {"full_name": "OWNER/REPO"},
        "ci_run": {
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abcdef123456",
            "html_url": "https://github.com/OWNER/REPO/actions",
        },
        "original_issue": {},
    }


def test_pipeline_run_ci_fix_accepts_repo_and_branch_overrides(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-ci-overrides"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(
        horde_cli,
        "get_repo_profile",
        lambda repo_id: {
            "repo_id": repo_id or "OWNER/REPO",
            "repo_url": f"https://github.com/{repo_id or 'OWNER/REPO'}",
            "token_ref": None,
        },
    )
    monkeypatch.setattr(horde_cli, "_resolve_local_head_sha", lambda: "ignored")

    exit_code = horde_cli.run_pipeline(
        pipeline_name="ci_scanner_pipeline",
        inputs_str='{"ci_run":{"head_sha":"manual-sha"}}',
        repo_id="ALT/REPO",
        branch="release",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "ci_scanner_pipeline"
    assert captured["inputs"]["repository"]["full_name"] == "ALT/REPO"
    assert captured["inputs"]["ci_run"]["head_branch"] == "release"
    assert captured["inputs"]["ci_run"]["head_sha"] == "manual-sha"


def test_pipeline_run_ci_fix_enriches_ci_run_from_github(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-ci-enriched"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(
        horde_cli,
        "get_repo_profile",
        lambda repo_id: {
            "repo_id": "OWNER/REPO",
            "repo_url": "https://github.com/OWNER/REPO",
            "token_ref": "repo.owner_repo.github_token",
        },
    )
    monkeypatch.setattr(horde_cli, "_get_secret_value", lambda key: "token-123")
    monkeypatch.setattr(
        horde_cli,
        "_fetch_latest_failed_ci_run",
        lambda repository_full_name, branch, github_token: {
            "id": 23,
            "name": "Build Docker",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abcdef123456",
            "html_url": "https://github.com/OWNER/REPO/actions/runs/23",
            "failed_jobs": [
                {
                    "name": "Build Docker",
                    "reason": "failed steps: push image",
                    "logs": "denied: installation not allowed to Create organization package",
                }
            ],
        },
    )

    exit_code = horde_cli.run_pipeline(
        pipeline_name="ci_scanner_pipeline",
        inputs_str="{}",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "ci_scanner_pipeline"
    assert captured["inputs"]["github_token"] == "token-123"
    assert captured["inputs"]["ci_run"]["id"] == 23
    assert captured["inputs"]["ci_run"]["name"] == "Build Docker"
    assert captured["inputs"]["ci_run"]["failed_jobs"][0]["name"] == "Build Docker"


def test_pipeline_run_issue_scanner_uses_default_repo_profile(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-issue-scanner-defaults"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)
    monkeypatch.setattr(
        horde_cli,
        "get_repo_profile",
        lambda repo_id: {
            "repo_id": "OWNER/REPO",
            "repo_url": "https://github.com/OWNER/REPO",
            "token_ref": "repo.owner_repo.github_token",
        },
    )
    monkeypatch.setattr(horde_cli, "_get_secret_value", lambda key: "token-123")

    exit_code = horde_cli.run_pipeline(
        pipeline_name="issue_scanner_pipeline",
        inputs_str="{}",
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "issue_scanner_pipeline"
    assert captured["inputs"]["repo_url"] == "https://github.com/OWNER/REPO"
    assert captured["inputs"]["github_token"] == "token-123"
    assert captured["inputs"]["repository"]["full_name"] == "OWNER/REPO"


def test_pipeline_run_respects_no_llm_flag(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_trigger(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
        captured["pipeline_name"] = pipeline_name
        captured["inputs"] = inputs
        return {"status": "started", "run_id": "run-no-llm"}

    monkeypatch.setattr(horde_cli, "trigger_pipeline", _fake_trigger)

    exit_code = horde_cli.run_pipeline(
        pipeline_name="feature_pipeline",
        inputs_str='{"issue":{"title":"Fix bug"}}',
        no_llm=True,
    )

    assert exit_code == horde_cli.EXIT_OK
    assert captured["pipeline_name"] == "feature_pipeline"
    assert captured["inputs"]["use_llm"] is False


def test_extract_log_error_excerpt_prefers_push_denied_error():
    log_text = """
    2026-03-28T21:10:40.3769781Z #12 2.406   git-man libbrotli1 libcom-err2 libcurl3t64-gnutls liberror-perl libexpat1
    2026-03-28T21:11:14.0000000Z ERROR: failed to build: failed to solve: failed to push ghcr.io/yxyxy/hordeforge:main: denied: installation not allowed to Create organization package
    """
    excerpt = horde_cli._extract_log_error_excerpt(log_text)
    assert "failed to push" in excerpt.lower()
    assert "denied" in excerpt.lower()


def test_run_llm_command_applies_llm_profile(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeLlmCli:
        def setup_parser(self):
            parser = argparse.ArgumentParser()
            parser.add_argument("--provider")
            parser.add_argument("--model")
            parser.add_argument("--api-key")
            parser.add_argument("--base-url")
            parser.add_argument("--plan", action="store_true")
            parser.add_argument("--act", action="store_true")
            parser.add_argument("--settings", action="store_true")
            parser.add_argument("command", nargs="?")
            return parser

        async def run_command(self, args):
            captured["provider"] = args.provider
            captured["model"] = args.model
            captured["api_key"] = getattr(args, "api_key", None)
            captured["command"] = args.command

    fake_module = ModuleType("cli.llm_cli")
    fake_module.LlmCli = _FakeLlmCli
    monkeypatch.setitem(sys.modules, "cli.llm_cli", fake_module)

    monkeypatch.setattr(
        horde_cli,
        "_get_llm_profile",
        lambda profile_name: {
            "profile_name": profile_name or "openai-main",
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": None,
            "api_key_ref": "llm.openai",
        },
    )
    monkeypatch.setattr(horde_cli, "_get_secret_value", lambda key: "api-key-123")

    args = SimpleNamespace(
        provider=None,
        model=None,
        api_key=None,
        base_url=None,
        plan=False,
        act=False,
        settings=False,
        llm_command="test",
        profile="openai-main",
    )

    exit_code = horde_cli.run_llm_command(args)
    assert exit_code == horde_cli.EXIT_OK
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-4o"
    assert captured["api_key"] == "api-key-123"
    assert captured["command"] == "test"


def test_run_llm_profile_add_qwen_code_auto_imports_default_oauth_file(monkeypatch, tmp_path):
    oauth_dir = tmp_path / ".qwen"
    oauth_dir.mkdir(parents=True, exist_ok=True)
    oauth_file = oauth_dir / "oauth_creds.json"
    oauth_payload = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "token_type": "Bearer",
        "resource_url": "portal.qwen.ai",
        "expiry_date": 1774753952314,
    }
    oauth_file.write_text(json.dumps(oauth_payload), encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    posted: list[tuple[str, dict[str, object]]] = []

    def _fake_gateway_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        posted.append((path, payload))
        return {"status": "ok"}

    monkeypatch.setattr(horde_cli, "_gateway_post", _fake_gateway_post)

    args = SimpleNamespace(
        llm_profile_command="add",
        profile_name="qwen-code-main",
        provider="qwen-code",
        model="qwen3-coder-plus",
        base_url=None,
        api_key=None,
        oauth_creds_file=None,
        oauth_creds_json=None,
        secret_ref=None,
        set_default=True,
    )

    exit_code = horde_cli.run_llm_profile_command(args)

    assert exit_code == horde_cli.EXIT_OK
    assert posted[0][0] == "/secrets"
    assert posted[0][1]["name"] == "llm.qwen-code-main.api_key"
    assert '"refresh_token": "refresh-token"' in str(posted[0][1]["value"])
    assert posted[1] == (
        "/llm/profiles",
        {
            "profile_name": "qwen-code-main",
            "provider": "qwen-code",
            "model": "qwen3-coder-plus",
            "base_url": None,
            "api_key_ref": "llm.qwen-code-main.api_key",
            "set_default": True,
        },
    )


def test_repo_without_subcommand_defaults_to_list(monkeypatch, capsys):
    monkeypatch.setattr(
        horde_cli,
        "list_repo_profiles",
        lambda: [
            {
                "repo_id": "OWNER/REPO",
                "repo_url": "https://github.com/OWNER/REPO",
                "token_ref": "repo.owner_repo.github_token",
                "is_default": True,
            }
        ],
    )
    args = SimpleNamespace(repo_command=None)

    exit_code = horde_cli.run_repo_command(args)
    output = capsys.readouterr().out

    assert exit_code == horde_cli.EXIT_OK
    assert (
        "* OWNER/REPO | https://github.com/OWNER/REPO | token_ref=repo.owner_repo.github_token"
        in output
    )


def test_repo_show_without_default_profile_has_clear_hint(monkeypatch, capsys):
    monkeypatch.setattr(horde_cli, "get_repo_profile", lambda repo_id: None)
    args = SimpleNamespace(repo_command="show", repo_id=None)

    exit_code = horde_cli.run_repo_command(args)
    error = capsys.readouterr().err

    assert exit_code == horde_cli.EXIT_ERROR
    assert "Add one via `horde repo add <owner/repo> --url ... --set-default`." in error


def test_repo_add_infers_repo_id_from_url(monkeypatch):
    saved_repo: dict[str, object] = {}

    def _fake_add_or_update_repo(
        repo_id: str, repo_url: str, token_ref: str | None = None, set_default: bool = False
    ) -> None:
        saved_repo.update(
            {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "token_ref": token_ref,
                "set_default": set_default,
            }
        )

    monkeypatch.setattr(horde_cli, "add_or_update_repo", _fake_add_or_update_repo)
    args = SimpleNamespace(
        repo_command="add",
        repo_id=None,
        url="https://github.com/OWNER/REPO",
        token=None,
        token_ref=None,
        set_default=True,
    )

    exit_code = horde_cli.run_repo_command(args)

    assert exit_code == horde_cli.EXIT_OK
    assert saved_repo == {
        "repo_id": "OWNER/REPO",
        "repo_url": "https://github.com/OWNER/REPO",
        "token_ref": None,
        "set_default": True,
    }
