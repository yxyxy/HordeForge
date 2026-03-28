import pytest
import requests

import cli


def test_parser_builds_status_command():
    parser = cli.build_parser()
    args = parser.parse_args(["status", "--run-id", "run-1"])
    assert args.command == "status"
    assert args.run_id == "run-1"


def test_parser_returns_usage_error_code_on_invalid_args():
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["status"])
    assert exc_info.value.code == cli.EXIT_USAGE_ERROR


def test_run_command_invalid_json_returns_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["cli.py", "run", "--pipeline", "init_pipeline", "--inputs", "not-json"],
    )

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "Invalid --inputs JSON" in captured.err


def test_status_command_success_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["cli.py", "status", "--run-id", "run-1"])
    monkeypatch.setattr(cli, "get_run_status", lambda _: {"run_id": "run-1", "status": "SUCCESS"})

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_OK
    assert '"run_id": "run-1"' in captured.out


def test_status_command_request_error_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["cli.py", "status", "--run-id", "run-2"])

    def _raise_request_error(_: str):
        raise requests.RequestException("request failed")

    monkeypatch.setattr(cli, "get_run_status", _raise_request_error)

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_ERROR
    assert "CLI command failed" in captured.err
