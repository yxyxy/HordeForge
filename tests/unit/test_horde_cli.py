from __future__ import annotations

from types import SimpleNamespace

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
