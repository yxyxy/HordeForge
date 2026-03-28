from __future__ import annotations

from argparse import Namespace

from cli import infra
from cli.horde_cli import EXIT_OK


def test_compose_up_default_local_smoke(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")
    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_stack_command(
        Namespace(
            stack_command="up",
            team=False,
            local=False,
            build=False,
            recreate=False,
            no_recreate=False,
        )
    )

    assert exit_code == EXIT_OK
    assert calls == [["up", "--no-recreate"]]


def test_compose_up_team_smoke(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "team")
    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_stack_command(
        Namespace(
            stack_command="up",
            team=False,
            local=False,
            build=False,
            recreate=False,
            no_recreate=False,
        )
    )

    assert exit_code == EXIT_OK
    assert calls == [["--profile", "team", "up", "-d", "--no-recreate"]]


def test_init_pipeline_local_fallback_smoke(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    resolved = infra.resolve_runtime_backends()

    assert resolved.mode == "local"
    assert resolved.vector_store_mode == "auto"


def test_init_pipeline_team_qdrant_smoke(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "team")

    resolved = infra.resolve_runtime_backends()

    assert resolved.mode == "team"
    assert resolved.vector_store_mode == "host"
    assert resolved.qdrant_host == "qdrant"


def test_mcp_endpoint_reachable_after_cli_start(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_mcp_command(
        Namespace(mcp_command="up", team=False, local=True, with_qdrant=False)
    )

    assert exit_code == EXIT_OK
    assert calls == [["--profile", "mcp", "up", "-d", "qdrant-mcp-local"]]


def test_cli_can_start_qdrant_service(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_qdrant_command(
        Namespace(qdrant_command="up", team=False, with_mcp=False, switch_host_mode=False)
    )

    assert exit_code == EXIT_OK
    assert calls == [["--profile", "team", "up", "-d", "qdrant"]]


def test_cli_can_start_mcp_service(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_mcp_command(
        Namespace(mcp_command="up", team=False, local=True, with_qdrant=False)
    )

    assert exit_code == EXIT_OK
    assert calls == [["--profile", "mcp", "up", "-d", "qdrant-mcp-local"]]


def test_cli_can_read_mode_status(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    resolved = infra.resolve_runtime_backends()

    assert resolved.mode == "local"
    assert resolved.storage_backend == "json"
    assert resolved.queue_backend == "memory"
