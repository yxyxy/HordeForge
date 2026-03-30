from __future__ import annotations

from argparse import Namespace

from cli import horde_cli


def test_default_mode_is_local_when_no_profile_selected(monkeypatch):
    monkeypatch.delenv("HORDEFORGE_INFRA_MODE", raising=False)
    monkeypatch.delenv("HORDEFORGE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("HORDEFORGE_QUEUE_BACKEND", raising=False)
    monkeypatch.delenv("HORDEFORGE_VECTOR_STORE_MODE", raising=False)

    from cli.infra import resolve_mode

    assert resolve_mode() == "local"


def test_local_mode_defaults_json_storage(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    from cli.infra import resolve_runtime_backends

    backends = resolve_runtime_backends()
    assert backends.storage_backend == "json"


def test_local_mode_defaults_memory_queue(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    from cli.infra import resolve_runtime_backends

    backends = resolve_runtime_backends()
    assert backends.queue_backend == "memory"


def test_local_mode_defaults_vector_auto(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    from cli.infra import resolve_runtime_backends

    backends = resolve_runtime_backends()
    assert backends.vector_store_mode == "auto"


def test_team_mode_selects_postgres_redis_host_qdrant(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "team")

    from cli.infra import resolve_runtime_backends

    backends = resolve_runtime_backends()
    assert backends.storage_backend == "postgres"
    assert backends.queue_backend == "redis"
    assert backends.vector_store_mode == "host"
    assert backends.qdrant_host == "qdrant"
    assert backends.qdrant_port == 6333


def test_infra_mode_show_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "mode", "show"])
    assert args.command == "infra"
    assert args.infra_command == "mode"
    assert args.mode_command == "show"


def test_init_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(
        ["init", "--repo-url", "https://github.com/example/repo", "--token", "t"]
    )
    assert args.command == "init"
    assert args.repo_url == "https://github.com/example/repo"
    assert args.token == "t"


def test_pipeline_run_accepts_repo_target_positional():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["pipeline", "run", "init", "yxyxy/HordeForge"])
    assert args.command == "pipeline"
    assert args.pipeline_command == "run"
    assert args.pipeline_name == "init"
    assert args.pipeline_target == "yxyxy/HordeForge"


def test_pipeline_run_accepts_no_llm_flag():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["pipeline", "run", "feature_pipeline", "--no-llm"])
    assert args.command == "pipeline"
    assert args.pipeline_command == "run"
    assert args.no_llm is True


def test_llm_profile_add_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(
        [
            "llm",
            "profile",
            "add",
            "openai-main",
            "--provider",
            "openai",
            "--model",
            "gpt-4o",
        ]
    )
    assert args.command == "llm"
    assert args.llm_command == "profile"
    assert args.llm_profile_command == "add"
    assert args.profile_name == "openai-main"


def test_infra_mode_set_local_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "mode", "set", "local"])
    assert args.command == "infra"
    assert args.infra_command == "mode"
    assert args.mode_command == "set"
    assert args.mode == "local"


def test_infra_mode_set_team_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "mode", "set", "team"])
    assert args.command == "infra"
    assert args.infra_command == "mode"
    assert args.mode_command == "set"
    assert args.mode == "team"


def test_infra_qdrant_up_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "qdrant", "up"])
    assert args.command == "infra"
    assert args.infra_command == "qdrant"
    assert args.qdrant_command == "up"


def test_infra_mcp_up_command_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "mcp", "up"])
    assert args.command == "infra"
    assert args.infra_command == "mcp"
    assert args.mcp_command == "up"


def test_infra_stack_up_flags_registered():
    parser = horde_cli.build_main_parser()
    args = parser.parse_args(["infra", "stack", "up", "--team", "--build", "--recreate"])
    assert args.command == "infra"
    assert args.infra_command == "stack"
    assert args.stack_command == "up"
    assert args.team is True
    assert args.build is True
    assert args.recreate is True


def test_local_stack_command_uses_plain_compose_up(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    from cli import infra

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

    assert exit_code == horde_cli.EXIT_OK
    assert calls == [["up", "--no-recreate"]]


def test_team_stack_command_uses_team_profile(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "team")

    from cli import infra

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

    assert exit_code == horde_cli.EXIT_OK
    assert calls == [["--profile", "team", "up", "-d", "--no-recreate"]]


def test_stack_up_supports_build_and_recreate_flags(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "team")

    from cli import infra

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_stack_command(
        Namespace(
            stack_command="up",
            team=False,
            local=False,
            build=True,
            recreate=True,
            no_recreate=False,
        )
    )

    assert exit_code == horde_cli.EXIT_OK
    assert calls == [["--profile", "team", "up", "-d", "--build", "--force-recreate"]]


def test_stack_up_rejects_conflicting_recreate_flags(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setenv("HORDEFORGE_INFRA_MODE", "local")

    from cli import infra

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_stack_command(
        Namespace(
            stack_command="up",
            team=False,
            local=False,
            build=False,
            recreate=True,
            no_recreate=True,
        )
    )

    assert exit_code == horde_cli.EXIT_ERROR
    assert calls == []


def test_qdrant_up_uses_correct_compose_invocation(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    from cli import infra

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_qdrant_command(
        Namespace(qdrant_command="up", team=False, with_mcp=False, switch_host_mode=False)
    )

    assert exit_code == horde_cli.EXIT_OK
    assert calls == [["--profile", "team", "up", "-d", "qdrant"]]


def test_mcp_up_uses_correct_compose_invocation(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run_compose(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    from cli import infra

    monkeypatch.setattr(infra, "run_compose_command", _fake_run_compose)

    exit_code = infra.handle_mcp_command(
        Namespace(mcp_command="up", team=False, local=False, with_qdrant=False)
    )

    assert exit_code == horde_cli.EXIT_OK
    assert calls == [["--profile", "mcp", "up", "-d", "qdrant-mcp-local"]]


def test_mode_show_reports_local_mcp_endpoint_when_available(monkeypatch, capsys):
    from cli import infra

    monkeypatch.setattr(
        infra,
        "resolve_runtime_backends",
        lambda: infra.RuntimeBackends(
            mode="local",
            storage_backend="json",
            queue_backend="memory",
            vector_store_mode="auto",
            gateway_url="http://localhost:8000",
            database_url="",
            redis_url="",
            qdrant_host="qdrant",
            qdrant_port=6333,
            mcp_endpoint="",
        ),
    )
    monkeypatch.setattr(
        infra,
        "_http_health",
        lambda url: url in {"http://localhost:8001"},
    )
    monkeypatch.setattr(infra, "_compose_output", lambda args: "")

    exit_code = infra.handle_mode_command(Namespace(mode_command="show"))
    output = capsys.readouterr().out

    assert exit_code == horde_cli.EXIT_OK
    assert "MCP endpoint: http://localhost:8001" in output


def test_mode_show_reports_mcp_when_container_is_running(monkeypatch, capsys):
    from cli import infra

    monkeypatch.setattr(
        infra,
        "resolve_runtime_backends",
        lambda: infra.RuntimeBackends(
            mode="local",
            storage_backend="json",
            queue_backend="memory",
            vector_store_mode="auto",
            gateway_url="http://localhost:8000",
            database_url="",
            redis_url="",
            qdrant_host="qdrant",
            qdrant_port=6333,
            mcp_endpoint="",
        ),
    )
    monkeypatch.setattr(
        infra,
        "_compose_output",
        lambda args: "qdrant-mcp-local" if args == ["ps", "qdrant-mcp-local"] else "",
    )
    monkeypatch.setattr(infra, "_http_health", lambda url: False)

    exit_code = infra.handle_mode_command(Namespace(mode_command="show"))
    output = capsys.readouterr().out

    assert exit_code == horde_cli.EXIT_OK
    assert "MCP endpoint: http://localhost:8001" in output


def test_detect_runtime_mode_team_when_team_services_running(monkeypatch):
    from cli import infra

    monkeypatch.setattr(
        infra,
        "_compose_output",
        lambda args: "db\nqdrant\n" if args == ["ps", "--services", "--status", "running"] else "",
    )

    assert infra.detect_runtime_mode("local") == "team"


def test_mode_show_reports_runtime_mode_mismatch(monkeypatch, capsys):
    from cli import infra

    monkeypatch.setattr(
        infra,
        "resolve_runtime_backends",
        lambda: infra.RuntimeBackends(
            mode="local",
            storage_backend="json",
            queue_backend="memory",
            vector_store_mode="auto",
            gateway_url="http://localhost:8000",
            database_url="",
            redis_url="",
            qdrant_host="qdrant",
            qdrant_port=6333,
            mcp_endpoint="",
        ),
    )
    monkeypatch.setattr(
        infra,
        "_compose_output",
        lambda args: "db\nqdrant\n" if args == ["ps", "--services", "--status", "running"] else "",
    )
    monkeypatch.setattr(infra, "_http_health", lambda url: False)

    exit_code = infra.handle_mode_command(Namespace(mode_command="show"))
    output = capsys.readouterr().out

    assert exit_code == horde_cli.EXIT_OK
    assert "Mode: local (configured)" in output
    assert "Runtime mode: team (detected from running containers)" in output
