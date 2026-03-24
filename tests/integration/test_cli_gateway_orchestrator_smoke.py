from __future__ import annotations

import json
from urllib.parse import urlparse

import requests
from fastapi.testclient import TestClient

import cli
from scheduler.gateway import RUNS, app


class ResponseAdapter:
    def __init__(self, response) -> None:
        self._response = response
        self.status_code = response.status_code

    def json(self) -> dict:
        return self._response.json()

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _install_cli_http_adapter(monkeypatch, client: TestClient) -> None:
    def _post(url: str, *, json: dict, timeout: float) -> ResponseAdapter:
        del timeout
        parsed = urlparse(url)
        response = client.post(parsed.path, json=json)
        return ResponseAdapter(response)

    def _get(url: str, *, timeout: float) -> ResponseAdapter:
        del timeout
        parsed = urlparse(url)
        response = client.get(parsed.path)
        return ResponseAdapter(response)

    monkeypatch.setattr(cli.requests, "post", _post)
    monkeypatch.setattr(cli.requests, "get", _get)


def test_cli_run_command_e2e_returns_api_payload_with_run_id_and_summary(monkeypatch, capsys):
    RUNS.clear()
    client = TestClient(app)
    _install_cli_http_adapter(monkeypatch, client)
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "run",
            "--pipeline",
            "init_pipeline",
            "--inputs",
            '{"repo_url":"https://github.com/yxyxy/hordeforge.git","github_token":"token"}',
        ],
    )

    exit_code = cli.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == cli.EXIT_OK
    assert payload["status"] == "started"
    assert payload["run_id"]
    assert payload["result"]["pipeline_name"] == "init_pipeline"
    assert payload["result"]["summary"]["run_id"] == payload["run_id"]
    assert payload["result"]["summary"]["step_count"] >= 1


def test_cli_status_command_e2e_returns_run_record_with_summary(monkeypatch, capsys):
    RUNS.clear()
    client = TestClient(app)
    _install_cli_http_adapter(monkeypatch, client)

    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "run",
            "--pipeline",
            "init_pipeline",
            "--inputs",
            '{"repo_url":"https://github.com/yxyxy/hordeforge.git","github_token":"token"}',
        ],
    )
    assert cli.main() == cli.EXIT_OK
    run_payload = json.loads(capsys.readouterr().out)
    run_id = run_payload["run_id"]

    monkeypatch.setattr("sys.argv", ["cli.py", "status", "--run-id", run_id])
    exit_code = cli.main()

    captured = capsys.readouterr()
    status_payload = json.loads(captured.out)
    assert exit_code == cli.EXIT_OK
    assert status_payload["run_id"] == run_id
    assert status_payload["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert status_payload["result"]["summary"]["run_id"] == run_id
