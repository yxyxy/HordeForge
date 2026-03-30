#!/usr/bin/env python3
"""
HordeForge CLI - Interactive AI development orchestrator in your terminal
"""

import argparse
import asyncio
import io
import json
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv is optional
    pass

# Add the project root to the Python path to import hordeforge_config
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.repo_store import (
    add_or_update_repo,
    build_repo_token_ref,
    get_repo_profile,
    list_repo_profiles,
    remove_repo,
    set_default_repo,
)
from hordeforge_config import RunConfig

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE_ERROR = 2
CONFIG = RunConfig.from_env()


class HordeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE_ERROR)


def load_pipeline(pipeline_file: str) -> dict:
    path = Path(pipeline_file)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "pipeline_name" not in data:
        raise ValueError(f"Invalid pipeline definition: {path}")
    return data


def trigger_pipeline(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
    correlation_id = str(uuid.uuid4())
    payload = {
        "pipeline_name": pipeline_name,
        "inputs": inputs,
        "source": source,
        "correlation_id": correlation_id,
    }
    url = f"{CONFIG.gateway_url}/run-pipeline"
    started_at = time.monotonic()
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=CONFIG.request_timeout_seconds,
        )
    except requests.ReadTimeout as exc:
        elapsed = time.monotonic() - started_at
        raise RuntimeError(
            "Gateway read timeout while calling /run-pipeline: "
            f"elapsed={elapsed:.2f}s configured_timeout={CONFIG.request_timeout_seconds:.2f}s "
            f"url={url}"
        ) from exc
    except requests.ConnectTimeout as exc:
        elapsed = time.monotonic() - started_at
        raise RuntimeError(
            "Gateway connect timeout while calling /run-pipeline: "
            f"elapsed={elapsed:.2f}s configured_timeout={CONFIG.request_timeout_seconds:.2f}s "
            f"url={url}"
        ) from exc
    except requests.RequestException as exc:
        elapsed = time.monotonic() - started_at
        raise RuntimeError(
            "Gateway request failed while calling /run-pipeline: "
            f"elapsed={elapsed:.2f}s configured_timeout={CONFIG.request_timeout_seconds:.2f}s "
            f"url={url} error={exc}"
        ) from exc
    response.raise_for_status()
    return response.json()


def get_run_status(run_id: str) -> dict:
    response = requests.get(
        f"{CONFIG.gateway_url}/runs/{run_id}",
        timeout=CONFIG.status_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def check_gateway_health() -> bool:
    try:
        response = requests.get(
            f"{CONFIG.gateway_url}/health",
            timeout=CONFIG.health_timeout_seconds,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def print_info(message: str) -> None:
    print(f"[INFO] {message}")


def print_warning(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def print_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def print_success(message: str) -> None:
    print(f"[OK] {message}")


def _gateway_get(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
    response = requests.get(
        f"{CONFIG.gateway_url}{path}",
        params=params,
        timeout=CONFIG.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _gateway_post(path: str, payload: dict[str, object]) -> dict[str, object]:
    response = requests.post(
        f"{CONFIG.gateway_url}{path}",
        json=payload,
        timeout=CONFIG.request_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _gateway_delete(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
    response = requests.delete(
        f"{CONFIG.gateway_url}{path}",
        params=params,
        timeout=CONFIG.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _build_llm_api_key_ref(profile_name: str) -> str:
    return f"llm.{profile_name.strip()}.api_key"


def _get_llm_profile(profile_name: str | None) -> dict[str, object] | None:
    try:
        params = {"profile_name": profile_name} if profile_name else None
        payload = _gateway_get("/llm/profiles", params=params)
    except requests.RequestException:
        return None
    profile = payload.get("profile")
    return profile if isinstance(profile, dict) else None


def _get_secret_value(key: str) -> str | None:
    try:
        payload = _gateway_get("/secrets", params={"name": key})
    except requests.RequestException:
        return None
    value = payload.get("value")
    return value if isinstance(value, str) else None


def build_main_parser() -> argparse.ArgumentParser:
    """Build the main Horde CLI parser."""
    parser = HordeArgumentParser(
        prog="horde",
        description="HordeForge CLI - AI development orchestrator in your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  horde task "Implement user authentication"           # Run a new task
  horde history                                       # Show task history
  horde config                                        # Show current configuration
  horde status                                        # Check system status
  horde pipeline list                                 # List available pipelines
  horde pipeline run init --repo-url https://...      # Run init pipeline
  horde --act "Deploy the application"               # Run in act mode
  horde --plan "Design the database schema"          # Run in plan mode
        """,
    )

    # Global options
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("-c", "--config", type=str, help="Path to configuration directory")
    parser.add_argument("--plan", action="store_true", help="Run in plan mode (analyze and plan)")
    parser.add_argument("--act", action="store_true", help="Run in act mode (execute actions)")
    parser.add_argument("--gateway-url", type=str, help="Gateway URL override")

    # Main command (interactive mode only - no positional prompt argument to avoid conflicts with subcommands)
    # The prompt will be handled by the default case when no subcommand is specified

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # Run command (for testing purposes)
    run_parser = subparsers.add_parser("run", help="Run a pipeline")
    run_parser.add_argument("--pipeline", type=str, help="Pipeline name to run")
    run_parser.add_argument("--inputs", type=str, help="JSON inputs for the pipeline")

    # Init command
    init_parser = subparsers.add_parser("init", help="Run init pipeline")
    init_parser.add_argument(
        "repo_target",
        nargs="?",
        help="Repository profile id (example: yxyxy/HordeForge)",
    )
    init_parser.add_argument("--repo-url", help="GitHub repository URL")
    init_parser.add_argument("--token", help="GitHub personal access token")

    # Status command (with --run-id option for testing)
    status_parser = subparsers.add_parser("status", help="Check system status")
    status_parser.add_argument(
        "--run-id", type=str, help="Run ID to check status for", required=True
    )

    # Task command
    task_parser = subparsers.add_parser("task", aliases=["t"], help="Run a new task")
    task_parser.add_argument("task_prompt", nargs="+", help="The task prompt")
    task_parser.add_argument("-a", "--act", action="store_true", help="Run in act mode")
    task_parser.add_argument("-p", "--plan", action="store_true", help="Run in plan mode")
    task_parser.add_argument("--timeout", type=int, help="Timeout in seconds")
    task_parser.add_argument("--model", type=str, help="Model to use for the task")
    task_parser.add_argument("--verbose", action="store_true", help="Show verbose output")

    # History command
    history_parser = subparsers.add_parser("history", aliases=["h"], help="Show task history")
    history_parser.add_argument(
        "-n", "--limit", type=int, default=10, help="Number of tasks to show (default: 10)"
    )
    history_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")

    # Config command
    subparsers.add_parser("config", help="Show current configuration")

    # Health command
    subparsers.add_parser("health", help="Check gateway health")

    # Pipeline command
    pipeline_parser = subparsers.add_parser("pipeline", help="Manage pipelines")
    pipeline_subparsers = pipeline_parser.add_subparsers(
        dest="pipeline_command", metavar="PIPELINE_COMMAND"
    )

    # Pipeline list
    pipeline_subparsers.add_parser("list", help="List available pipelines")

    # Pipeline run
    pipeline_run_parser = pipeline_subparsers.add_parser("run", help="Run a pipeline")
    pipeline_run_parser.add_argument("pipeline_name", help="Pipeline name to run")
    pipeline_run_parser.add_argument(
        "pipeline_target",
        nargs="?",
        help="Optional repository profile id for init pipeline",
    )
    pipeline_run_parser.add_argument(
        "--repo",
        type=str,
        help="Repository profile id override (defaults to configured repo profile)",
    )
    pipeline_run_parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Branch for CI context (ci_fix_pipeline, default: main)",
    )
    pipeline_run_parser.add_argument(
        "--head-sha",
        type=str,
        help="Commit SHA for CI context (ci_fix_pipeline, defaults to local HEAD)",
    )
    pipeline_run_parser.add_argument(
        "--inputs", type=str, default="{}", help="JSON object with pipeline inputs"
    )
    pipeline_run_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM usage for this pipeline run (sets inputs.use_llm=false)",
    )
    pipeline_run_parser.add_argument(
        "--repo-url", type=str, help="Repository URL (for init pipeline)"
    )
    pipeline_run_parser.add_argument("--token", type=str, help="GitHub token (for init pipeline)")

    # Repo profiles command
    repo_parser = subparsers.add_parser("repo", help="Manage repository profiles")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", metavar="REPO_COMMAND")

    repo_add_parser = repo_subparsers.add_parser("add", help="Add or update repository profile")
    repo_add_parser.add_argument(
        "repo_id",
        nargs="?",
        help="Repository id (example: yxyxy/HordeForge). If omitted, derived from --url.",
    )
    repo_add_parser.add_argument("--url", required=True, help="Repository URL")
    repo_add_parser.add_argument("--token", help="GitHub token to store in secrets.json")
    repo_add_parser.add_argument(
        "--token-ref",
        help="Existing token key from secrets.json (alternative to --token)",
    )
    repo_add_parser.add_argument(
        "--set-default",
        action="store_true",
        help="Set this profile as default for init runs",
    )
    repo_subparsers.add_parser("list", help="List repository profiles")
    repo_use_parser = repo_subparsers.add_parser("use", help="Set default repository profile")
    repo_use_parser.add_argument("repo_id", help="Repository id")
    repo_show_parser = repo_subparsers.add_parser("show", help="Show repository profile")
    repo_show_parser.add_argument("repo_id", nargs="?", help="Repository id (default if omitted)")
    repo_remove_parser = repo_subparsers.add_parser("remove", help="Remove repository profile")
    repo_remove_parser.add_argument("repo_id", help="Repository id")
    repo_remove_parser.add_argument(
        "--delete-token",
        action="store_true",
        help="Also delete referenced token from secrets store",
    )

    # Secrets command
    secret_parser = subparsers.add_parser("secret", help="Manage gateway secret store")
    secret_subparsers = secret_parser.add_subparsers(
        dest="secret_command", metavar="SECRET_COMMAND"
    )
    secret_set_parser = secret_subparsers.add_parser("set", help="Set secret value")
    secret_set_parser.add_argument("name", help="Secret key")
    secret_set_parser.add_argument("value", help="Secret value")
    secret_subparsers.add_parser("list", help="List secret keys")
    secret_remove_parser = secret_subparsers.add_parser("remove", help="Remove secret value")
    secret_remove_parser.add_argument("name", help="Secret key")

    # Infra command
    infra_parser = subparsers.add_parser("infra", help="Manage optional local/team infrastructure")
    infra_subparsers = infra_parser.add_subparsers(dest="infra_command", metavar="INFRA_COMMAND")

    # infra mode
    infra_mode_parser = infra_subparsers.add_parser("mode", help="Show or set infrastructure mode")
    infra_mode_subparsers = infra_mode_parser.add_subparsers(
        dest="mode_command", metavar="MODE_COMMAND"
    )
    infra_mode_subparsers.add_parser("show", help="Show effective infrastructure mode and backends")
    infra_mode_set_parser = infra_mode_subparsers.add_parser("set", help="Set infrastructure mode")
    infra_mode_set_parser.add_argument("mode", choices=["local", "team"], help="Target mode")
    infra_mode_set_parser.add_argument(
        "--save", action="store_true", help="Persist mode configuration"
    )
    infra_mode_set_parser.add_argument(
        "--profile",
        type=str,
        help="Profile name to store mode defaults in ~/.hordeforge/profiles",
    )

    # infra qdrant
    infra_qdrant_parser = infra_subparsers.add_parser("qdrant", help="Manage Qdrant service")
    infra_qdrant_subparsers = infra_qdrant_parser.add_subparsers(
        dest="qdrant_command", metavar="QDRANT_COMMAND"
    )
    infra_qdrant_up_parser = infra_qdrant_subparsers.add_parser("up", help="Start Qdrant")
    infra_qdrant_up_parser.add_argument(
        "--with-mcp", action="store_true", help="Also start MCP bridge"
    )
    infra_qdrant_up_parser.add_argument("--team", action="store_true", help="Use team MCP bridge")
    infra_qdrant_up_parser.add_argument(
        "--switch-host-mode",
        action="store_true",
        help="Switch HORDEFORGE_VECTOR_STORE_MODE to host for current session",
    )
    infra_qdrant_down_parser = infra_qdrant_subparsers.add_parser("down", help="Stop Qdrant")
    infra_qdrant_down_parser.add_argument(
        "--switch-auto-mode",
        action="store_true",
        help="Switch HORDEFORGE_VECTOR_STORE_MODE to auto for current session",
    )
    infra_qdrant_subparsers.add_parser("status", help="Show Qdrant status")

    # infra mcp
    infra_mcp_parser = infra_subparsers.add_parser("mcp", help="Manage MCP bridge service")
    infra_mcp_subparsers = infra_mcp_parser.add_subparsers(
        dest="mcp_command", metavar="MCP_COMMAND"
    )
    infra_mcp_up_parser = infra_mcp_subparsers.add_parser("up", help="Start MCP bridge")
    infra_mcp_up_parser.add_argument(
        "--local", action="store_true", help="Use local MCP bridge profile"
    )
    infra_mcp_up_parser.add_argument(
        "--team", action="store_true", help="Use team MCP bridge profile"
    )
    infra_mcp_up_parser.add_argument(
        "--with-qdrant", action="store_true", help="Start Qdrant first"
    )
    infra_mcp_down_parser = infra_mcp_subparsers.add_parser("down", help="Stop MCP bridge")
    infra_mcp_down_parser.add_argument(
        "--local", action="store_true", help="Use local MCP bridge profile"
    )
    infra_mcp_down_parser.add_argument(
        "--team", action="store_true", help="Use team MCP bridge profile"
    )
    infra_mcp_status_parser = infra_mcp_subparsers.add_parser(
        "status", help="Show MCP bridge status"
    )
    infra_mcp_status_parser.add_argument(
        "--local", action="store_true", help="Check local MCP bridge"
    )
    infra_mcp_status_parser.add_argument(
        "--team", action="store_true", help="Check team MCP bridge"
    )

    # infra stack
    infra_stack_parser = infra_subparsers.add_parser(
        "stack", help="Manage compose stack as one command"
    )
    infra_stack_subparsers = infra_stack_parser.add_subparsers(
        dest="stack_command", metavar="STACK_COMMAND"
    )
    for stack_action in ("up", "down", "status"):
        stack_action_parser = infra_stack_subparsers.add_parser(
            stack_action, help=f"{stack_action} stack"
        )
        stack_action_parser.add_argument("--local", action="store_true", help="Force local mode")
        stack_action_parser.add_argument("--team", action="store_true", help="Force team mode")
        if stack_action == "up":
            stack_action_parser.add_argument(
                "--build", action="store_true", help="Build images before starting"
            )
            stack_action_parser.add_argument(
                "--recreate",
                action="store_true",
                help="Force container recreation (use with care)",
            )
            stack_action_parser.add_argument(
                "--no-recreate",
                action="store_true",
                help="Do not recreate containers (default behavior)",
            )

    # LLM command (existing functionality)
    llm_parser = subparsers.add_parser("llm", help="LLM operations")
    llm_parser.add_argument(
        "--provider",
        choices=[
            "openai",
            "anthropic",
            "google",
            "ollama",
            "gemini",
            "openrouter",
            "bedrock",
            "vertex",
            "lmstudio",
            "deepseek",
            "fireworks",
            "together",
            "qwen",
            "qwen-code",
            "mistral",
            "huggingface",
            "litellm",
            "moonshot",
            "groq",
            "claude_code",
        ],
        help="LLM provider to use",
    )
    llm_parser.add_argument("--model", type=str, help="Model name to use")
    llm_parser.add_argument("--api-key", type=str, help="API key for the provider")
    llm_parser.add_argument("--base-url", type=str, help="Base URL for local providers")
    llm_parser.add_argument("--profile", type=str, help="LLM profile name from gateway store")
    llm_parser.add_argument("--plan", action="store_true", help="Plan mode - analyze and plan")
    llm_parser.add_argument("--act", action="store_true", help="Act mode - execute actions")
    llm_parser.add_argument("--settings", action="store_true", help="Open settings configuration")

    # Add subcommands for LLM
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", metavar="LLM_COMMAND")
    llm_subparsers.add_parser("chat", help="Interactive chat with LLM")
    llm_subparsers.add_parser("plan", help="Plan mode - analyze and plan")
    llm_subparsers.add_parser("act", help="Act mode - execute actions")
    llm_subparsers.add_parser("test", help="Test provider connectivity")
    llm_subparsers.add_parser("list-providers", help="List available providers")
    llm_subparsers.add_parser("settings", help="Manage provider settings")
    llm_subparsers.add_parser("tokens", help="Show token usage")
    llm_subparsers.add_parser("cost", help="Show cost information")
    llm_subparsers.add_parser("budget", help="Show budget information")
    llm_profile_parser = llm_subparsers.add_parser("profile", help="Manage LLM profiles")
    llm_profile_subparsers = llm_profile_parser.add_subparsers(
        dest="llm_profile_command", metavar="LLM_PROFILE_COMMAND"
    )
    llm_profile_add_parser = llm_profile_subparsers.add_parser("add", help="Add/update LLM profile")
    llm_profile_add_parser.add_argument("profile_name", help="Profile name")
    llm_profile_add_parser.add_argument(
        "--provider",
        required=True,
        choices=[
            "openai",
            "anthropic",
            "google",
            "ollama",
            "gemini",
            "openrouter",
            "bedrock",
            "vertex",
            "lmstudio",
            "deepseek",
            "fireworks",
            "together",
            "qwen",
            "qwen-code",
            "mistral",
            "huggingface",
            "litellm",
            "moonshot",
            "groq",
            "claude_code",
        ],
        help="LLM provider",
    )
    llm_profile_add_parser.add_argument("--model", required=True, help="Model name")
    llm_profile_add_parser.add_argument("--base-url", type=str, help="Optional base URL")
    llm_profile_add_parser.add_argument("--api-key", type=str, help="API key to store")
    llm_profile_add_parser.add_argument(
        "--oauth-creds-file",
        type=str,
        help="Path to Qwen Code oauth_creds.json (for --provider qwen-code)",
    )
    llm_profile_add_parser.add_argument(
        "--oauth-creds-json",
        type=str,
        help="Raw OAuth credentials JSON string (for --provider qwen-code)",
    )
    llm_profile_add_parser.add_argument(
        "--secret-ref",
        type=str,
        help="Existing secret key from secrets store",
    )
    llm_profile_add_parser.add_argument(
        "--set-default",
        action="store_true",
        help="Set as default LLM profile",
    )
    llm_profile_subparsers.add_parser("list", help="List LLM profiles")
    llm_profile_use_parser = llm_profile_subparsers.add_parser(
        "use", help="Set default LLM profile"
    )
    llm_profile_use_parser.add_argument("profile_name", help="Profile name")
    llm_profile_show_parser = llm_profile_subparsers.add_parser("show", help="Show LLM profile")
    llm_profile_show_parser.add_argument("profile_name", nargs="?", help="Profile name")
    llm_profile_remove_parser = llm_profile_subparsers.add_parser(
        "remove", help="Remove LLM profile"
    )
    llm_profile_remove_parser.add_argument("profile_name", help="Profile name")
    llm_profile_remove_parser.add_argument(
        "--delete-secret",
        action="store_true",
        help="Also delete referenced API key from secrets store",
    )

    return parser


def build_parser() -> argparse.ArgumentParser:
    """Alias for build_main_parser to support legacy tests."""
    return build_main_parser()


def run_task_interactive(prompt: str, args) -> int:
    """Run a task in interactive mode."""
    print_info(f"Running task: {prompt}")
    print_info("Submitting feature pipeline run through gateway...")

    try:
        inputs = {"prompt": prompt}

        if hasattr(args, "act") and args.act:
            inputs["mode"] = "act"
        elif hasattr(args, "plan") and args.plan:
            inputs["mode"] = "plan"

        if hasattr(args, "model") and args.model:
            inputs["model"] = args.model

        result = trigger_pipeline("feature_pipeline", inputs, source="horde_task")
        run_id = result.get("run_id")
        if run_id:
            print_success(f"Task submitted successfully (run_id={run_id})")
        else:
            print_success("Task submitted successfully")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    except Exception as e:
        print_error(f"Task failed: {e}")
        return EXIT_ERROR


def show_history(limit: int = 10, page: int = 1) -> int:
    """Show task history."""
    normalized_limit = max(1, int(limit))
    normalized_page = max(1, int(page))
    offset = (normalized_page - 1) * normalized_limit

    print_info(f"Showing task history (limit: {normalized_limit}, page: {normalized_page})")

    try:
        response = requests.get(
            f"{CONFIG.gateway_url}/runs",
            params={"offset": offset, "limit": normalized_limit},
            timeout=CONFIG.status_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        print_error(f"Failed to fetch history: {e}")
        return EXIT_ERROR

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not items:
        print_info("No runs found.")
        return EXIT_OK

    print("Recent runs:")
    for run in items:
        run_id = run.get("run_id", "-")
        pipeline_name = run.get("pipeline_name", "-")
        status = run.get("status", "-")
        started_at = run.get("started_at") or run.get("created_at") or "-"
        print(f"- {run_id} | {pipeline_name} | {status} | {started_at}")

    return EXIT_OK


def show_config() -> int:
    """Show current configuration."""
    print_info("Current Configuration:")
    print(f"Gateway URL: {CONFIG.gateway_url}")
    print(f"Pipelines Directory: {CONFIG.pipelines_dir}")
    print(f"Rules Directory: {CONFIG.rules_dir}")
    print(f"Storage Directory: {CONFIG.storage_dir}")
    print(f"Queue Backend: {CONFIG.queue_backend}")
    print(f"Max Parallel Workers: {CONFIG.max_parallel_workers}")
    print(f"Request Timeout: {CONFIG.request_timeout_seconds}s")
    print(f"Status Timeout: {CONFIG.status_timeout_seconds}s")
    print(f"Health Timeout: {CONFIG.health_timeout_seconds}s")

    return EXIT_OK


def check_status() -> int:
    """Check system status."""
    print_info("Checking system status...")

    health_ok = check_gateway_health()
    if health_ok:
        print_success("Gateway: Healthy")
    else:
        print_error("Gateway: Unhealthy")

    # Check other services would go here
    print_info("Database: Checking...")
    print_info("Redis: Checking...")
    print_info("Qdrant: Checking...")

    return EXIT_OK if health_ok else EXIT_ERROR


def list_pipelines() -> int:
    """List available pipelines."""
    print_info("Available Pipelines:")

    # Look for pipeline files in the pipelines directory
    pipelines_dir = Path(CONFIG.pipelines_dir)
    if pipelines_dir.exists():
        for pipeline_file in pipelines_dir.glob("*.yaml"):
            pipeline_name = pipeline_file.stem
            print(f"- {pipeline_name}")
    else:
        print_error(f"Pipelines directory not found: {pipelines_dir}")
        return EXIT_ERROR

    return EXIT_OK


def run_pipeline(
    pipeline_name: str,
    inputs_str: str,
    repo_url: str = None,
    token: str = None,
    pipeline_target: str = None,
    repo_id: str = None,
    branch: str = None,
    head_sha: str = None,
    no_llm: bool = False,
) -> int:
    """Run a specific pipeline."""
    try:
        resolved_pipeline_name = "init_pipeline" if pipeline_name == "init" else pipeline_name
        inputs = _parse_pipeline_inputs(inputs_str)

        resolved_repo_id = repo_id.strip() if isinstance(repo_id, str) and repo_id.strip() else None
        if (
            resolved_repo_id is None
            and isinstance(pipeline_target, str)
            and pipeline_target.strip()
        ):
            resolved_repo_id = pipeline_target.strip()

        if resolved_pipeline_name == "init_pipeline" and resolved_repo_id and not repo_url:
            profile = get_repo_profile(resolved_repo_id)
            if profile is None:
                print_error(f"Repository profile not found: {resolved_repo_id}")
                return EXIT_ERROR
            profile_repo_url = profile.get("repo_url")
            if isinstance(profile_repo_url, str) and profile_repo_url.strip():
                repo_url = profile_repo_url.strip()
            token_ref = profile.get("token_ref")
            if not token and isinstance(token_ref, str) and token_ref.strip():
                token = _get_secret_value(token_ref.strip())

        if resolved_pipeline_name == "ci_fix_pipeline":
            _apply_ci_fix_defaults(
                inputs=inputs,
                repo_id=resolved_repo_id,
                branch=branch,
                head_sha=head_sha,
            )
        if resolved_pipeline_name == "issue_scanner_pipeline":
            _apply_issue_scanner_defaults(
                inputs=inputs,
                repo_id=resolved_repo_id,
            )

        if no_llm:
            inputs["use_llm"] = False

        if repo_url:
            inputs["repo_url"] = repo_url
        if token:
            inputs["github_token"] = token

        if resolved_pipeline_name == "init_pipeline" and "repo_url" not in inputs:
            print_error("repo_url is required for init pipeline. Use --repo-url or profile target.")
            return EXIT_ERROR

        if resolved_pipeline_name == "init_pipeline":
            _ensure_repo_profile_from_init_inputs(
                repo_url=inputs.get("repo_url"),
                token=inputs.get("github_token"),
            )

        result = trigger_pipeline(resolved_pipeline_name, inputs)
        print_success(f"Pipeline '{resolved_pipeline_name}' started successfully!")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    except ValueError as e:
        print_error(str(e))
        return EXIT_ERROR
    except Exception as e:
        print_error(f"Pipeline failed: {e}")
        return EXIT_ERROR


def _resolve_local_head_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if sha else None


def _ensure_repo_profile_from_init_inputs(repo_url: object, token: object) -> None:
    if not isinstance(repo_url, str) or not repo_url.strip():
        return
    repo_id = _repo_full_name_from_url(repo_url)
    if not repo_id:
        return
    if get_repo_profile(repo_id) is not None:
        return

    token_ref: str | None = None
    if isinstance(token, str) and token.strip():
        token_ref = build_repo_token_ref(repo_id)
        try:
            _gateway_post("/secrets", {"name": token_ref, "value": token.strip()})
        except requests.RequestException as exc:
            print_warning(f"Could not persist init token to gateway secret store: {exc}")
            token_ref = None

    add_or_update_repo(
        repo_id=repo_id,
        repo_url=repo_url.strip(),
        token_ref=token_ref,
        set_default=False,
    )
    print_info(f"Auto-saved repository profile '{repo_id}' from init inputs.")


def _repo_full_name_from_url(repo_url: str | None) -> str | None:
    if not isinstance(repo_url, str):
        return None
    raw = repo_url.strip()
    if not raw:
        return None
    if raw.startswith("git@github.com:"):
        suffix = raw[len("git@github.com:") :]
        return suffix.removesuffix(".git").strip("/") or None
    parsed = urlparse(raw)
    if parsed.netloc.lower() != "github.com":
        return None
    path = parsed.path.strip("/")
    if not path:
        return None
    return path.removesuffix(".git")


def _ensure_object(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _fetch_latest_failed_ci_run(
    repository_full_name: str,
    branch: str,
    github_token: str,
) -> dict[str, object] | None:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token.strip():
        headers["Authorization"] = f"token {github_token.strip()}"

    try:
        response = requests.get(
            f"https://api.github.com/repos/{repository_full_name}/actions/runs",
            headers=headers,
            params={"branch": branch, "status": "completed", "per_page": 20},
            timeout=CONFIG.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print_warning(f"Could not fetch latest CI run from GitHub: {exc}")
        return None

    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return None

    failed_conclusions = {"failure", "cancelled", "timed_out", "action_required"}
    for run in runs:
        if not isinstance(run, dict):
            continue
        conclusion = str(run.get("conclusion", "")).strip().lower()
        if conclusion not in failed_conclusions:
            continue
        run_id = run.get("id")
        if not isinstance(run_id, int):
            continue

        ci_run: dict[str, object] = {
            "id": run_id,
            "name": run.get("name") or run.get("display_title") or "workflow",
            "status": run.get("status") or "completed",
            "conclusion": run.get("conclusion") or "failure",
            "head_branch": run.get("head_branch") or branch,
            "head_sha": run.get("head_sha"),
            "html_url": run.get("html_url")
            or f"https://github.com/{repository_full_name}/actions/runs/{run_id}",
        }
        failed_jobs = _fetch_failed_jobs_for_run(
            repository_full_name=repository_full_name,
            run_id=run_id,
            github_token=github_token,
        )
        if failed_jobs:
            ci_run["failed_jobs"] = failed_jobs
        return ci_run
    return None


def _fetch_failed_jobs_for_run(
    repository_full_name: str, run_id: int, github_token: str
) -> list[dict[str, object]]:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token.strip():
        headers["Authorization"] = f"token {github_token.strip()}"

    try:
        response = requests.get(
            f"https://api.github.com/repos/{repository_full_name}/actions/runs/{run_id}/jobs",
            headers=headers,
            params={"per_page": 100},
            timeout=CONFIG.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print_warning(f"Could not fetch CI jobs for run {run_id}: {exc}")
        return []

    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return []

    failure_status = {"failure", "cancelled", "timed_out", "action_required"}
    failed_jobs: list[dict[str, object]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        conclusion = str(job.get("conclusion", "")).strip().lower()
        status = str(job.get("status", "")).strip().lower()
        if conclusion not in failure_status and status != "failed":
            continue

        steps = job.get("steps")
        failed_steps: list[str] = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_conclusion = str(step.get("conclusion", "")).strip().lower()
                if step_conclusion in failure_status:
                    step_name = str(step.get("name", "")).strip() or "unknown-step"
                    failed_steps.append(step_name)

        reason = (
            f"failed steps: {', '.join(failed_steps)}"
            if failed_steps
            else f"job failed (status={status or 'unknown'}, conclusion={conclusion or 'unknown'})"
        )
        log_excerpt = ""
        job_id = job.get("id")
        if isinstance(job_id, int):
            log_excerpt = _fetch_job_log_excerpt(
                repository_full_name=repository_full_name,
                job_id=job_id,
                github_token=github_token,
            )
        logs = (
            f"job_url={job.get('html_url', 'n/a')}; "
            f"run_id={run_id}; "
            f"failed_steps={', '.join(failed_steps) if failed_steps else 'none'}"
        )
        if log_excerpt:
            logs = f"{logs}; excerpt={log_excerpt}"
        failed_jobs.append(
            {
                "name": job.get("name") or "unknown-job",
                "reason": reason,
                "logs": logs,
            }
        )

    return failed_jobs


def _fetch_job_log_excerpt(repository_full_name: str, job_id: int, github_token: str) -> str:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token.strip():
        headers["Authorization"] = f"token {github_token.strip()}"
    try:
        response = requests.get(
            f"https://api.github.com/repos/{repository_full_name}/actions/jobs/{job_id}/logs",
            headers=headers,
            timeout=CONFIG.request_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    content_type = str(response.headers.get("Content-Type", "")).lower()
    if "text/plain" in content_type or "application/json" in content_type:
        return _extract_log_error_excerpt(response.text)

    try:
        archive = zipfile.ZipFile(io.BytesIO(response.content))
    except (zipfile.BadZipFile, OSError):
        return ""

    for name in archive.namelist():
        try:
            with archive.open(name) as handle:
                raw = handle.read()
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        excerpt = _extract_log_error_excerpt(text)
        if excerpt:
            return excerpt
    return ""


def _extract_log_error_excerpt(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    scored_patterns: list[tuple[int, tuple[str, ...]]] = [
        (
            100,
            (
                "failed to push",
                "installation not allowed",
                "denied:",
                "permission denied",
                "insufficient_scope",
            ),
        ),
        (
            80,
            (
                "failed to solve",
                "failed to build",
                "error:",
            ),
        ),
        (
            60,
            (
                "exception",
                "traceback",
                "fatal",
            ),
        ),
        (
            40,
            (
                "failed",
                "failure",
                "denied",
            ),
        ),
    ]
    noise_tokens = ("liberror-perl", "libcurl", "libexpat", "apt-get install", "fetch ")

    best_line = ""
    best_score = -1
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in noise_tokens):
            continue
        for score, pattern_group in scored_patterns:
            if any(token in lower for token in pattern_group):
                if score > best_score:
                    best_line = line
                    best_score = score
                break
    if best_line:
        return best_line[:240]
    return lines[-1][:240]


def _apply_ci_fix_defaults(
    inputs: dict[str, object],
    repo_id: str | None,
    branch: str | None,
    head_sha: str | None,
) -> None:
    profile = get_repo_profile(repo_id)

    repository = _ensure_object(inputs.get("repository"))
    ci_run = _ensure_object(inputs.get("ci_run"))
    original_issue = _ensure_object(inputs.get("original_issue"))

    full_name = repository.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        profile_repo_id = profile.get("repo_id") if isinstance(profile, dict) else None
        profile_repo_url = profile.get("repo_url") if isinstance(profile, dict) else None
        derived_full_name = (
            profile_repo_id.strip()
            if isinstance(profile_repo_id, str) and profile_repo_id.strip()
            else _repo_full_name_from_url(profile_repo_url)
        )
        if not derived_full_name:
            raise ValueError(
                "Repository is not set. Use --repo, provide --inputs with repository.full_name, "
                "or configure a default repo via `horde repo add ... --set-default`."
            )
        repository["full_name"] = derived_full_name
    else:
        repository["full_name"] = full_name.strip()

    if not inputs.get("github_token") and isinstance(profile, dict):
        token_ref = profile.get("token_ref")
        if isinstance(token_ref, str) and token_ref.strip():
            token_value = _get_secret_value(token_ref.strip())
            if isinstance(token_value, str) and token_value.strip():
                inputs["github_token"] = token_value.strip()

    selected_branch = branch.strip() if isinstance(branch, str) and branch.strip() else "main"

    if not ci_run.get("id"):
        github_token = inputs.get("github_token")
        if isinstance(github_token, str) and github_token.strip():
            fetched_ci_run = _fetch_latest_failed_ci_run(
                repository_full_name=str(repository["full_name"]),
                branch=selected_branch,
                github_token=github_token,
            )
            if isinstance(fetched_ci_run, dict):
                for key in (
                    "id",
                    "name",
                    "status",
                    "conclusion",
                    "head_branch",
                    "head_sha",
                    "html_url",
                    "failed_jobs",
                ):
                    if key in fetched_ci_run and not ci_run.get(key):
                        ci_run[key] = fetched_ci_run[key]

    ci_run.setdefault("status", "completed")
    ci_run.setdefault("conclusion", "failure")
    ci_run.setdefault("head_branch", selected_branch)
    ci_run.setdefault("html_url", f"https://github.com/{repository['full_name']}/actions")

    if not ci_run.get("head_sha"):
        resolved_sha = (
            head_sha.strip()
            if isinstance(head_sha, str) and head_sha.strip()
            else _resolve_local_head_sha()
        )
        if resolved_sha:
            ci_run["head_sha"] = resolved_sha

    inputs["repository"] = repository
    inputs["ci_run"] = ci_run
    inputs["original_issue"] = original_issue


def _apply_issue_scanner_defaults(
    inputs: dict[str, object],
    repo_id: str | None,
) -> None:
    profile = get_repo_profile(repo_id)
    if not isinstance(profile, dict):
        raise ValueError(
            "Repository is not set. Use --repo, provide --inputs with repo_url, "
            "or configure a default repo via `horde repo add ... --set-default`."
        )

    profile_repo_url = profile.get("repo_url")
    if "repo_url" not in inputs and isinstance(profile_repo_url, str) and profile_repo_url.strip():
        inputs["repo_url"] = profile_repo_url.strip()

    if not inputs.get("github_token"):
        token_ref = profile.get("token_ref")
        if isinstance(token_ref, str) and token_ref.strip():
            token_value = _get_secret_value(token_ref.strip())
            if isinstance(token_value, str) and token_value.strip():
                inputs["github_token"] = token_value.strip()

    repository = _ensure_object(inputs.get("repository"))
    full_name = repository.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        profile_repo_id = profile.get("repo_id")
        derived_full_name = (
            profile_repo_id.strip()
            if isinstance(profile_repo_id, str) and profile_repo_id.strip()
            else _repo_full_name_from_url(profile_repo_url)
        )
        if isinstance(derived_full_name, str) and derived_full_name.strip():
            repository["full_name"] = derived_full_name.strip()
    if repository:
        inputs["repository"] = repository

    if not isinstance(inputs.get("repo_url"), str) or not str(inputs.get("repo_url")).strip():
        raise ValueError(
            "repo_url is required for issue_scanner_pipeline. "
            "Set default repo via `horde repo add ... --set-default` or pass --inputs with repo_url."
        )


def _parse_pipeline_inputs(raw_inputs: str | None) -> dict[str, object]:
    raw = (raw_inputs or "{}").strip()

    if raw == "-":
        raw = sys.stdin.read().strip()
    elif raw.startswith("@"):
        input_path = Path(raw[1:]).expanduser()
        if not input_path.exists():
            raise ValueError(f"Inputs file not found: {input_path}")
        raw = input_path.read_text(encoding="utf-8").strip()

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid JSON in inputs. "
            "Use --inputs @file.json or --inputs - (stdin) for shell-safe input."
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError("Pipeline inputs must be a JSON object.")
    return parsed


def run_llm_command(args) -> int:
    """Handle LLM operations using the existing LLM CLI."""
    # Import the LLM CLI functionality
    from cli.llm_cli import LlmCli

    # Create LLM CLI instance and pass the arguments
    llm_cli = LlmCli()
    llm_parser = llm_cli.setup_parser()

    # Build arguments list for LLM CLI
    llm_args_list = []

    resolved_provider = args.provider
    resolved_model = args.model
    resolved_api_key = args.api_key
    resolved_base_url = args.base_url

    profile = _get_llm_profile(args.profile if hasattr(args, "profile") else None)
    if profile:
        if not resolved_provider:
            resolved_provider = profile.get("provider")
        if not resolved_model:
            resolved_model = profile.get("model")
        if not resolved_base_url:
            resolved_base_url = profile.get("base_url")
        if not resolved_api_key:
            api_key_ref = profile.get("api_key_ref")
            if isinstance(api_key_ref, str) and api_key_ref.strip():
                resolved_api_key = _get_secret_value(api_key_ref.strip())
                if not resolved_api_key:
                    print_error(f"Missing API key in secrets store: {api_key_ref}")
                    return EXIT_ERROR

    if resolved_provider:
        llm_args_list.extend(["--provider", resolved_provider])
    if resolved_model:
        llm_args_list.extend(["--model", resolved_model])
    if resolved_api_key:
        llm_args_list.extend(["--api-key", resolved_api_key])
    if resolved_base_url:
        llm_args_list.extend(["--base-url", resolved_base_url])
    if args.plan:
        llm_args_list.append("--plan")
    if args.act:
        llm_args_list.append("--act")
    if args.settings:
        llm_args_list.append("--settings")
    if args.llm_command:
        llm_args_list.append(args.llm_command)

    # Parse the arguments for LLM CLI
    try:
        llm_args = llm_parser.parse_args(llm_args_list)
        asyncio.run(llm_cli.run_command(llm_args))
        return EXIT_OK
    except SystemExit:
        return EXIT_ERROR


def run_llm_profile_command(args) -> int:
    try:
        return _run_llm_profile_command_impl(args)
    except requests.RequestException as exc:
        print_error(f"Failed to reach gateway for LLM profile operation: {exc}")
        return EXIT_ERROR


def _run_llm_profile_command_impl(args) -> int:
    if args.llm_profile_command == "add":
        if args.api_key and args.secret_ref:
            print_error("Use either --api-key or --secret-ref, not both.")
            return EXIT_ERROR
        if args.oauth_creds_file and args.oauth_creds_json:
            print_error("Use either --oauth-creds-file or --oauth-creds-json, not both.")
            return EXIT_ERROR
        api_key_ref = args.secret_ref
        if args.provider == "qwen-code":
            oauth_creds_raw = None
            if args.oauth_creds_json:
                oauth_creds_raw = args.oauth_creds_json.strip()
            elif args.oauth_creds_file:
                oauth_path = Path(args.oauth_creds_file).expanduser()
                if not oauth_path.exists():
                    print_error(f"OAuth credentials file not found: {oauth_path}")
                    return EXIT_ERROR
                oauth_creds_raw = oauth_path.read_text(encoding="utf-8").strip()
            elif not args.api_key and not args.secret_ref:
                default_oauth_path = Path.home() / ".qwen" / "oauth_creds.json"
                if not default_oauth_path.exists():
                    print_error(
                        "Qwen Code OAuth credentials not found at "
                        f"{default_oauth_path}. Use --oauth-creds-file or --oauth-creds-json."
                    )
                    return EXIT_ERROR
                oauth_creds_raw = default_oauth_path.read_text(encoding="utf-8").strip()

            if oauth_creds_raw:
                try:
                    parsed = json.loads(oauth_creds_raw)
                except json.JSONDecodeError:
                    print_error("Invalid JSON in Qwen Code OAuth credentials.")
                    return EXIT_ERROR
                if not isinstance(parsed, dict):
                    print_error("Qwen Code OAuth credentials must be a JSON object.")
                    return EXIT_ERROR
                if not parsed.get("refresh_token"):
                    print_error("Qwen Code OAuth credentials must include refresh_token.")
                    return EXIT_ERROR
                api_key_ref = _build_llm_api_key_ref(args.profile_name)
                _gateway_post(
                    "/secrets",
                    {"name": api_key_ref, "value": oauth_creds_raw},
                )

        if args.api_key:
            api_key_ref = _build_llm_api_key_ref(args.profile_name)
            _gateway_post(
                "/secrets",
                {"name": api_key_ref, "value": args.api_key},
            )
        _gateway_post(
            "/llm/profiles",
            {
                "profile_name": args.profile_name,
                "provider": args.provider,
                "model": args.model,
                "base_url": args.base_url,
                "api_key_ref": api_key_ref,
                "set_default": args.set_default,
            },
        )
        print_success(f"Saved LLM profile '{args.profile_name}'.")
        if api_key_ref:
            print_info(f"API key ref: {api_key_ref}")
        return EXIT_OK

    if args.llm_profile_command == "list":
        payload = _gateway_get("/llm/profiles")
        profiles = payload.get("profiles", [])
        if not profiles:
            print_info("No LLM profiles found.")
            return EXIT_OK
        for profile in profiles:
            marker = "*" if profile.get("is_default") else " "
            profile_name = profile.get("profile_name", "-")
            provider = profile.get("provider", "-")
            model = profile.get("model", "-")
            api_key_ref = profile.get("api_key_ref") or "-"
            print(f"{marker} {profile_name} | {provider}:{model} | api_key_ref={api_key_ref}")
        return EXIT_OK

    if args.llm_profile_command == "use":
        try:
            _gateway_post(f"/llm/profiles/{args.profile_name}/default", {})
            print_success(f"Default LLM profile set to '{args.profile_name}'.")
            return EXIT_OK
        except requests.RequestException:
            pass
        print_error(f"LLM profile not found: {args.profile_name}")
        return EXIT_ERROR

    if args.llm_profile_command == "show":
        profile = _get_llm_profile(args.profile_name)
        if profile is None:
            print_error("LLM profile not found.")
            return EXIT_ERROR
        print(json.dumps(profile, indent=2))
        return EXIT_OK

    if args.llm_profile_command == "remove":
        try:
            payload = _gateway_delete(f"/llm/profiles/{args.profile_name}")
            api_key_ref = payload.get("api_key_ref")
        except requests.RequestException:
            print_error(f"LLM profile not found: {args.profile_name}")
            return EXIT_ERROR
        if args.delete_secret and api_key_ref:
            _gateway_delete(f"/secrets/{api_key_ref}")
        print_success(f"LLM profile '{args.profile_name}' removed.")
        return EXIT_OK

    print_error("Unknown llm profile command")
    return EXIT_ERROR


def run_repo_command(args) -> int:
    if args.repo_command is None:
        args.repo_command = "list"

    if args.repo_command == "add":
        resolved_repo_id = (
            args.repo_id.strip() if isinstance(args.repo_id, str) and args.repo_id.strip() else None
        )
        if resolved_repo_id is None:
            resolved_repo_id = _repo_full_name_from_url(args.url)
        if not resolved_repo_id:
            print_error(
                "Could not infer repository id. Pass it explicitly: horde repo add OWNER/REPO --url ..."
            )
            return EXIT_ERROR
        if args.token and args.token_ref:
            print_error("Use either --token or --token-ref, not both.")
            return EXIT_ERROR
        token_ref = args.token_ref
        if args.token:
            token_ref = build_repo_token_ref(resolved_repo_id)
            _gateway_post("/secrets", {"name": token_ref, "value": args.token})
        add_or_update_repo(
            repo_id=resolved_repo_id,
            repo_url=args.url,
            token_ref=token_ref,
            set_default=args.set_default,
        )
        print_success(f"Saved repository profile '{resolved_repo_id}'.")
        if token_ref:
            print_info(f"Token ref: {token_ref}")
        return EXIT_OK

    if args.repo_command == "list":
        profiles = list_repo_profiles()
        if not profiles:
            print_info("No repository profiles found.")
            return EXIT_OK
        for profile in profiles:
            marker = "*" if profile.get("is_default") else " "
            repo_id = profile.get("repo_id", "-")
            repo_url = profile.get("repo_url", "-")
            token_ref = profile.get("token_ref") or "-"
            print(f"{marker} {repo_id} | {repo_url} | token_ref={token_ref}")
        return EXIT_OK

    if args.repo_command == "use":
        if set_default_repo(args.repo_id):
            print_success(f"Default repository profile set to '{args.repo_id}'.")
            return EXIT_OK
        print_error(f"Repository profile not found: {args.repo_id}")
        return EXIT_ERROR

    if args.repo_command == "show":
        profile = get_repo_profile(args.repo_id)
        if profile is None:
            if args.repo_id:
                print_error(f"Repository profile not found: {args.repo_id}")
            else:
                print_error(
                    "Repository profile not found. "
                    "Add one via `horde repo add <owner/repo> --url ... --set-default`."
                )
            return EXIT_ERROR
        print(json.dumps(profile, indent=2))
        return EXIT_OK

    if args.repo_command == "remove":
        token_ref = remove_repo(args.repo_id)
        if token_ref is None:
            print_error(f"Repository profile not found: {args.repo_id}")
            return EXIT_ERROR
        if args.delete_token and token_ref:
            _gateway_delete(f"/secrets/{token_ref}")
        print_success(f"Repository profile '{args.repo_id}' removed.")
        return EXIT_OK

    print_error("Unknown repo command")
    return EXIT_ERROR


def run_secret_command(args) -> int:
    try:
        if args.secret_command == "set":
            _gateway_post("/secrets", {"name": args.name, "value": args.value})
            print_success(f"Secret '{args.name}' saved.")
            return EXIT_OK
        if args.secret_command == "list":
            payload = _gateway_get("/secrets")
            keys = payload.get("keys", [])
            if not keys:
                print_info("No secrets found.")
                return EXIT_OK
            for key in keys:
                print(f"- {key}")
            return EXIT_OK
        if args.secret_command == "remove":
            try:
                _gateway_delete(f"/secrets/{args.name}")
                print_success(f"Secret '{args.name}' removed.")
                return EXIT_OK
            except requests.RequestException:
                pass
            print_error(f"Secret not found: {args.name}")
            return EXIT_ERROR
        print_error("Unknown secret command")
        return EXIT_ERROR
    except requests.RequestException as exc:
        print_error(f"Failed to reach gateway for secret operation: {exc}")
        return EXIT_ERROR


def main() -> int:
    """Main entry point for the Horde CLI."""
    parser = build_main_parser()

    # Parse arguments
    args = parser.parse_args()

    # Update config if gateway URL is provided
    if args.gateway_url:
        CONFIG.gateway_url = args.gateway_url

    # Handle different commands
    if args.command == "run":
        # Handle run command for testing
        if not args.pipeline:
            print_error("Pipeline name is required for run command")
            return EXIT_USAGE_ERROR

        try:
            inputs = json.loads(args.inputs) if args.inputs else {}
            result = trigger_pipeline(args.pipeline, inputs)
            print(json.dumps(result, indent=2))
            return EXIT_OK
        except json.JSONDecodeError as e:
            print_error(f"Invalid --inputs JSON: {e}")
            return EXIT_USAGE_ERROR
        except Exception as e:
            print_error(f"Run command failed: {e}")
            return EXIT_ERROR

    elif args.command == "status":
        # Handle status command with optional run-id
        if args.run_id:
            try:
                # Import the function dynamically to allow for monkeypatching
                from cli import get_run_status as cli_get_run_status

                result = cli_get_run_status(args.run_id)
                print(json.dumps(result, indent=2))
                return EXIT_OK
            except requests.RequestException as e:
                print_error(f"CLI command failed: {e}")
                return EXIT_ERROR
        else:
            return check_status()

    elif args.command == "task":
        prompt = " ".join(args.task_prompt)
        return run_task_interactive(prompt, args)

    elif args.command == "history":
        return show_history(args.limit, args.page)

    elif args.command == "config":
        return show_config()

    elif args.command == "health":
        health_ok = check_gateway_health()
        if health_ok:
            print_success("Gateway is healthy")
            return EXIT_OK
        else:
            print_error("Gateway is unhealthy")
            return EXIT_ERROR

    elif args.command == "init":
        return run_pipeline(
            "init_pipeline",
            "{}",
            args.repo_url,
            args.token,
            args.repo_target,
        )

    elif args.command == "pipeline":
        if args.pipeline_command == "list":
            return list_pipelines()
        elif args.pipeline_command == "run":
            return run_pipeline(
                args.pipeline_name,
                args.inputs,
                args.repo_url,
                args.token,
                args.pipeline_target,
                args.repo,
                args.branch,
                args.head_sha,
                args.no_llm,
            )
        else:
            parser.print_help()
            return EXIT_USAGE_ERROR

    elif args.command == "repo":
        return run_repo_command(args)

    elif args.command == "secret":
        return run_secret_command(args)

    elif args.command == "llm":
        if args.llm_command == "profile":
            return run_llm_profile_command(args)
        return run_llm_command(args)

    elif args.command == "infra":
        from cli.infra import handle_infra_command

        return handle_infra_command(args)

    else:
        # No command specified - show help
        parser.print_help()
        return EXIT_USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
