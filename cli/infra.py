from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import requests

from cli.horde_cli import EXIT_ERROR, EXIT_OK


@dataclass(frozen=True, slots=True)
class RuntimeBackends:
    mode: str
    storage_backend: str
    queue_backend: str
    vector_store_mode: str
    gateway_url: str
    database_url: str
    redis_url: str
    qdrant_host: str
    qdrant_port: int
    mcp_endpoint: str


def resolve_mode(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    explicit_mode = env.get("HORDEFORGE_INFRA_MODE", "").strip().lower()
    if explicit_mode in {"local", "team"}:
        return explicit_mode

    storage_backend = env.get("HORDEFORGE_STORAGE_BACKEND", "json").strip().lower()
    queue_backend = env.get("HORDEFORGE_QUEUE_BACKEND", "memory").strip().lower()
    vector_store_mode = env.get("HORDEFORGE_VECTOR_STORE_MODE", "auto").strip().lower()
    if storage_backend == "postgres" or queue_backend == "redis" or vector_store_mode == "host":
        return "team"
    return "local"


def resolve_runtime_backends(environ: Mapping[str, str] | None = None) -> RuntimeBackends:
    env = environ or os.environ
    mode = resolve_mode(env)
    explicit_mode = env.get("HORDEFORGE_INFRA_MODE", "").strip().lower()

    local_defaults = {
        "storage_backend": "json",
        "queue_backend": "memory",
        "vector_store_mode": "auto",
    }
    team_defaults = {
        "storage_backend": "postgres",
        "queue_backend": "redis",
        "vector_store_mode": "host",
    }
    defaults = local_defaults if mode == "local" else team_defaults

    if explicit_mode in {"local", "team"}:
        storage_backend = defaults["storage_backend"]
        queue_backend = defaults["queue_backend"]
        vector_store_mode = defaults["vector_store_mode"]
    else:
        storage_backend = (
            env.get("HORDEFORGE_STORAGE_BACKEND", defaults["storage_backend"]).strip().lower()
        )
        queue_backend = (
            env.get("HORDEFORGE_QUEUE_BACKEND", defaults["queue_backend"]).strip().lower()
        )
        vector_store_mode = (
            env.get("HORDEFORGE_VECTOR_STORE_MODE", defaults["vector_store_mode"]).strip().lower()
        )
    gateway_url = env.get("HORDEFORGE_GATEWAY_URL", "http://localhost:8000").rstrip("/")
    database_url = env.get("HORDEFORGE_DATABASE_URL", "").strip()
    redis_url = env.get("HORDEFORGE_REDIS_URL", "").strip()
    qdrant_host = env.get("QDRANT_HOST", "qdrant").strip() or "qdrant"
    qdrant_port_raw = env.get("QDRANT_PORT", "6333").strip()
    mcp_endpoint = env.get("HORDEFORGE_MCP_ENDPOINT", "").strip()
    try:
        qdrant_port = int(qdrant_port_raw)
    except ValueError:
        qdrant_port = 6333

    return RuntimeBackends(
        mode=mode,
        storage_backend=storage_backend,
        queue_backend=queue_backend,
        vector_store_mode=vector_store_mode,
        gateway_url=gateway_url,
        database_url=database_url,
        redis_url=redis_url,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        mcp_endpoint=mcp_endpoint,
    )


def _env_updates_for_mode(mode: str) -> dict[str, str]:
    if mode == "local":
        return {
            "HORDEFORGE_INFRA_MODE": "local",
            "HORDEFORGE_STORAGE_BACKEND": "json",
            "HORDEFORGE_QUEUE_BACKEND": "memory",
            "HORDEFORGE_VECTOR_STORE_MODE": "auto",
            "HORDEFORGE_DATABASE_URL": "",
            "HORDEFORGE_REDIS_URL": "",
        }
    return {
        "HORDEFORGE_INFRA_MODE": "team",
        "HORDEFORGE_STORAGE_BACKEND": "postgres",
        "HORDEFORGE_QUEUE_BACKEND": "redis",
        "HORDEFORGE_VECTOR_STORE_MODE": "host",
        "HORDEFORGE_DATABASE_URL": (
            "postgresql+psycopg://hordeforge:hordeforge@db:5432/hordeforge"
        ),
        "HORDEFORGE_REDIS_URL": "redis://redis:6379/0",
        "QDRANT_HOST": "qdrant",
        "QDRANT_PORT": "6333",
    }


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending_keys = dict(updates)
    output_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        normalized_key = key.strip()
        if normalized_key in pending_keys:
            output_lines.append(f"{normalized_key}={pending_keys.pop(normalized_key)}")
        else:
            output_lines.append(line)

    for key, value in pending_keys.items():
        output_lines.append(f"{key}={value}")

    path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _save_profile(profile_name: str, mode: str, updates: dict[str, str]) -> Path:
    profile_dir = Path(os.path.expanduser("~/.hordeforge/profiles"))
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f"{profile_name}.json"
    payload: dict[str, object] = {}
    if profile_path.exists():
        try:
            loaded = json.loads(profile_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = {}
    payload["infra_mode"] = mode
    payload["infra_env"] = updates
    profile_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return profile_path


def run_compose_command(compose_args: list[str]) -> int:
    command = ["docker", "compose", *compose_args]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _compose_output(compose_args: list[str]) -> str:
    command = ["docker", "compose", *compose_args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _running_compose_services() -> set[str]:
    output = _compose_output(["ps", "--services", "--status", "running"])
    if not output:
        return set()
    return {line.strip().lower() for line in output.splitlines() if line.strip()}


def detect_runtime_mode(configured_mode: str) -> str:
    running_services = _running_compose_services()
    team_services = {"db", "redis", "qdrant", "qdrant-mcp"}
    if running_services & team_services:
        return "team"
    if "qdrant-mcp-local" in running_services:
        return "local"
    return configured_mode


def _http_health(url: str) -> bool:
    try:
        response = requests.get(url, timeout=2.5)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def _mode_set(args) -> int:
    updates = _env_updates_for_mode(args.mode)
    if not args.save:
        for key, value in updates.items():
            os.environ[key] = value
        print(f"Mode switched to {args.mode} for current session.")
        return EXIT_OK

    if args.profile:
        profile_path = _save_profile(args.profile, args.mode, updates)
        print(f"Saved mode '{args.mode}' to profile: {profile_path}")
        return EXIT_OK

    env_path = Path(".env")
    _upsert_env_file(env_path, updates)
    print(f"Saved mode '{args.mode}' to {env_path.resolve()}")
    return EXIT_OK


def _mode_show() -> int:
    backends = resolve_runtime_backends()
    runtime_mode = detect_runtime_mode(backends.mode)
    if runtime_mode == backends.mode:
        print(f"Mode: {backends.mode}")
    else:
        print(f"Mode: {backends.mode} (configured)")
        print(f"Runtime mode: {runtime_mode} (detected from running containers)")
    print(f"Storage backend: {backends.storage_backend}")
    print(f"Queue backend: {backends.queue_backend}")
    print(f"Vector store mode: {backends.vector_store_mode}")
    print(f"Gateway URL: {backends.gateway_url}")
    print(f"External DB: {'enabled' if backends.database_url else 'disabled'}")
    print(f"External Redis: {'enabled' if backends.redis_url else 'disabled'}")
    qdrant_enabled = _http_health("http://localhost:6333/healthz")
    print(f"External Qdrant: {'enabled' if qdrant_enabled else 'disabled'}")
    mcp_running_local = "mcp" in _compose_output(["ps", "qdrant-mcp-local"]).lower()
    mcp_running_team = "mcp" in _compose_output(["ps", "qdrant-mcp"]).lower()
    mcp_endpoint = (
        "http://localhost:8001" if (mcp_running_local or mcp_running_team) else "disabled"
    )
    if mcp_endpoint == "disabled":
        mcp_candidates = [backends.mcp_endpoint] if backends.mcp_endpoint else []
        if "http://localhost:8001" not in mcp_candidates:
            mcp_candidates.append("http://localhost:8001")
        for endpoint in mcp_candidates:
            if endpoint and _http_health(endpoint):
                mcp_endpoint = endpoint
                break
    print(f"MCP endpoint: {mcp_endpoint}")
    return EXIT_OK


def handle_mode_command(args) -> int:
    if args.mode_command == "show":
        return _mode_show()
    if args.mode_command == "set":
        return _mode_set(args)
    return EXIT_ERROR


def handle_qdrant_command(args) -> int:
    if args.qdrant_command == "up":
        command: list[str] = ["--profile", "team", "up", "-d", "qdrant"]
        if args.with_mcp and args.team:
            command.append("qdrant-mcp")
        if args.with_mcp and not args.team:
            rc = run_compose_command(command)
            if rc != 0:
                return EXIT_ERROR
            rc = run_compose_command(["--profile", "mcp", "up", "-d", "qdrant-mcp-local"])
            return EXIT_OK if rc == 0 else EXIT_ERROR
        if args.switch_host_mode:
            os.environ["HORDEFORGE_VECTOR_STORE_MODE"] = "host"
        return EXIT_OK if run_compose_command(command) == 0 else EXIT_ERROR

    if args.qdrant_command == "down":
        command: list[str] = ["--profile", "team", "stop", "qdrant"]
        if args.switch_auto_mode:
            os.environ["HORDEFORGE_VECTOR_STORE_MODE"] = "auto"
        return EXIT_OK if run_compose_command(command) == 0 else EXIT_ERROR

    if args.qdrant_command == "status":
        output = _compose_output(["ps", "qdrant"])
        is_running = bool(output and "qdrant" in output.lower())
        healthy = _http_health("http://localhost:6333/healthz")
        backends = resolve_runtime_backends()
        print(f"Container: {'running' if is_running else 'stopped'}")
        print(f"Health: {'healthy' if healthy else 'unreachable'}")
        print(f"Vector mode: {backends.vector_store_mode}")
        return EXIT_OK

    return EXIT_ERROR


def handle_mcp_command(args) -> int:
    use_team = bool(args.team)
    use_local = bool(args.local or not args.team)

    if args.mcp_command == "up":
        if args.with_qdrant:
            qdrant_rc = run_compose_command(["--profile", "team", "up", "-d", "qdrant"])
            if qdrant_rc != 0:
                return EXIT_ERROR
        if use_team and not args.local:
            return (
                EXIT_OK
                if run_compose_command(["--profile", "team", "up", "-d", "qdrant-mcp"]) == 0
                else EXIT_ERROR
            )
        if use_local:
            return (
                EXIT_OK
                if run_compose_command(["--profile", "mcp", "up", "-d", "qdrant-mcp-local"]) == 0
                else EXIT_ERROR
            )

    if args.mcp_command == "down":
        if use_team and not args.local:
            return (
                EXIT_OK
                if run_compose_command(["--profile", "team", "stop", "qdrant-mcp"]) == 0
                else EXIT_ERROR
            )
        if use_local:
            return (
                EXIT_OK
                if run_compose_command(["--profile", "mcp", "stop", "qdrant-mcp-local"]) == 0
                else EXIT_ERROR
            )

    if args.mcp_command == "status":
        if use_team and not args.local:
            output = _compose_output(["ps", "qdrant-mcp"])
            endpoint = "http://localhost:8001"
        else:
            output = _compose_output(["ps", "qdrant-mcp-local"])
            endpoint = "http://localhost:8001"
        is_running = bool(output and "mcp" in output.lower())
        print(f"MCP: {'enabled' if is_running else 'disabled'}")
        print(f"Endpoint: {endpoint if is_running else 'disabled'}")
        print("Transport: streamable-http")
        print(f"Collection: {os.getenv('MCP_COLLECTION_NAME', 'hordeforge_repo')}")
        return EXIT_OK

    return EXIT_ERROR


def handle_stack_command(args) -> int:
    local_override = bool(args.local)
    team_override = bool(args.team)
    mode = "team" if team_override else "local" if local_override else resolve_mode()

    if args.stack_command == "up":
        build_flag = bool(getattr(args, "build", False))
        recreate_flag = bool(getattr(args, "recreate", False))
        no_recreate_flag = bool(getattr(args, "no_recreate", False))
        if recreate_flag and no_recreate_flag:
            print("Cannot use --recreate and --no-recreate together.")
            return EXIT_ERROR

        up_flags: list[str] = []
        if build_flag:
            up_flags.append("--build")
        if recreate_flag:
            up_flags.append("--force-recreate")
        elif no_recreate_flag or not recreate_flag:
            up_flags.append("--no-recreate")

        if mode == "team":
            command = ["--profile", "team", "up", "-d", *up_flags]
        else:
            command = ["up", *up_flags]
        return EXIT_OK if run_compose_command(command) == 0 else EXIT_ERROR

    if args.stack_command == "down":
        command = ["--profile", "team", "down"] if mode == "team" else ["down"]
        return EXIT_OK if run_compose_command(command) == 0 else EXIT_ERROR

    if args.stack_command == "status":
        command = ["--profile", "team", "ps"] if mode == "team" else ["ps"]
        return EXIT_OK if run_compose_command(command) == 0 else EXIT_ERROR

    return EXIT_ERROR


def handle_infra_command(args) -> int:
    if args.infra_command == "mode":
        return handle_mode_command(args)
    if args.infra_command == "qdrant":
        return handle_qdrant_command(args)
    if args.infra_command == "mcp":
        return handle_mcp_command(args)
    if args.infra_command == "stack":
        return handle_stack_command(args)
    return EXIT_ERROR
