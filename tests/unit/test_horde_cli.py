from __future__ import annotations

import argparse
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
    monkeypatch.setattr(horde_cli, "get_secret_value", lambda key: "stored-token")

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
        "get_llm_profile",
        lambda profile_name: {
            "profile_name": profile_name or "openai-main",
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": None,
            "api_key_ref": "llm.openai",
        },
    )
    monkeypatch.setattr(horde_cli, "get_secret_value", lambda key: "api-key-123")

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
