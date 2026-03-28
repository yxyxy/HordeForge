#!/usr/bin/env python3
"""
HordeForge CLI - Interactive AI development orchestrator in your terminal
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

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
    add_or_update_llm_profile,
    add_or_update_repo,
    build_llm_api_key_ref,
    build_repo_token_ref,
    get_llm_profile,
    get_repo_profile,
    get_secret_value,
    list_llm_profiles,
    list_repo_profiles,
    list_secret_keys,
    remove_llm_profile,
    remove_repo,
    remove_secret_value,
    set_default_llm_profile,
    set_default_repo,
    set_secret_value,
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
    response = requests.post(
        f"{CONFIG.gateway_url}/run-pipeline",
        json=payload,
        timeout=CONFIG.request_timeout_seconds,
    )
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
        "--inputs", type=str, default="{}", help="JSON object with pipeline inputs"
    )
    pipeline_run_parser.add_argument(
        "--repo-url", type=str, help="Repository URL (for init pipeline)"
    )
    pipeline_run_parser.add_argument("--token", type=str, help="GitHub token (for init pipeline)")

    # Repo profiles command
    repo_parser = subparsers.add_parser("repo", help="Manage repository profiles")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", metavar="REPO_COMMAND")

    repo_add_parser = repo_subparsers.add_parser("add", help="Add or update repository profile")
    repo_add_parser.add_argument("repo_id", help="Repository id (example: yxyxy/HordeForge)")
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
    secret_parser = subparsers.add_parser("secret", help="Manage local secret store")
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
    llm_parser.add_argument("--profile", type=str, help="LLM profile name from local store")
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
) -> int:
    """Run a specific pipeline."""
    try:
        resolved_pipeline_name = "init_pipeline" if pipeline_name == "init" else pipeline_name
        inputs = json.loads(inputs_str) if inputs_str else {}

        if resolved_pipeline_name == "init_pipeline" and pipeline_target and not repo_url:
            profile = get_repo_profile(pipeline_target)
            if profile is None:
                print_error(f"Repository profile not found: {pipeline_target}")
                return EXIT_ERROR
            profile_repo_url = profile.get("repo_url")
            if isinstance(profile_repo_url, str) and profile_repo_url.strip():
                repo_url = profile_repo_url.strip()
            token_ref = profile.get("token_ref")
            if not token and isinstance(token_ref, str) and token_ref.strip():
                token = get_secret_value(token_ref.strip())

        if repo_url:
            inputs["repo_url"] = repo_url
        if token:
            inputs["github_token"] = token

        if resolved_pipeline_name == "init_pipeline" and "repo_url" not in inputs:
            print_error("repo_url is required for init pipeline. Use --repo-url or profile target.")
            return EXIT_ERROR

        result = trigger_pipeline(resolved_pipeline_name, inputs)
        print_success(f"Pipeline '{resolved_pipeline_name}' started successfully!")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in inputs: {e}")
        return EXIT_ERROR
    except Exception as e:
        print_error(f"Pipeline failed: {e}")
        return EXIT_ERROR


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

    profile = get_llm_profile(args.profile if hasattr(args, "profile") else None)
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
                resolved_api_key = get_secret_value(api_key_ref.strip())
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
    if args.llm_profile_command == "add":
        if args.api_key and args.secret_ref:
            print_error("Use either --api-key or --secret-ref, not both.")
            return EXIT_ERROR
        api_key_ref = args.secret_ref
        if args.api_key:
            api_key_ref = build_llm_api_key_ref(args.profile_name)
            set_secret_value(api_key_ref, args.api_key)
        add_or_update_llm_profile(
            profile_name=args.profile_name,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_ref=api_key_ref,
            set_default=args.set_default,
        )
        print_success(f"Saved LLM profile '{args.profile_name}'.")
        if api_key_ref:
            print_info(f"API key ref: {api_key_ref}")
        return EXIT_OK

    if args.llm_profile_command == "list":
        profiles = list_llm_profiles()
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
        if set_default_llm_profile(args.profile_name):
            print_success(f"Default LLM profile set to '{args.profile_name}'.")
            return EXIT_OK
        print_error(f"LLM profile not found: {args.profile_name}")
        return EXIT_ERROR

    if args.llm_profile_command == "show":
        profile = get_llm_profile(args.profile_name)
        if profile is None:
            print_error("LLM profile not found.")
            return EXIT_ERROR
        print(json.dumps(profile, indent=2))
        return EXIT_OK

    if args.llm_profile_command == "remove":
        api_key_ref = remove_llm_profile(args.profile_name)
        if api_key_ref is None:
            print_error(f"LLM profile not found: {args.profile_name}")
            return EXIT_ERROR
        if args.delete_secret and api_key_ref:
            remove_secret_value(api_key_ref)
        print_success(f"LLM profile '{args.profile_name}' removed.")
        return EXIT_OK

    print_error("Unknown llm profile command")
    return EXIT_ERROR


def run_repo_command(args) -> int:
    if args.repo_command == "add":
        if args.token and args.token_ref:
            print_error("Use either --token or --token-ref, not both.")
            return EXIT_ERROR
        token_ref = args.token_ref
        if args.token:
            token_ref = build_repo_token_ref(args.repo_id)
            set_secret_value(token_ref, args.token)
        add_or_update_repo(
            repo_id=args.repo_id,
            repo_url=args.url,
            token_ref=token_ref,
            set_default=args.set_default,
        )
        print_success(f"Saved repository profile '{args.repo_id}'.")
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
            print_error("Repository profile not found.")
            return EXIT_ERROR
        print(json.dumps(profile, indent=2))
        return EXIT_OK

    if args.repo_command == "remove":
        token_ref = remove_repo(args.repo_id)
        if token_ref is None:
            print_error(f"Repository profile not found: {args.repo_id}")
            return EXIT_ERROR
        if args.delete_token and token_ref:
            remove_secret_value(token_ref)
        print_success(f"Repository profile '{args.repo_id}' removed.")
        return EXIT_OK

    print_error("Unknown repo command")
    return EXIT_ERROR


def run_secret_command(args) -> int:
    if args.secret_command == "set":
        set_secret_value(args.name, args.value)
        print_success(f"Secret '{args.name}' saved.")
        return EXIT_OK
    if args.secret_command == "list":
        keys = list_secret_keys()
        if not keys:
            print_info("No secrets found.")
            return EXIT_OK
        for key in keys:
            print(f"- {key}")
        return EXIT_OK
    if args.secret_command == "remove":
        removed = remove_secret_value(args.name)
        if removed:
            print_success(f"Secret '{args.name}' removed.")
            return EXIT_OK
        print_error(f"Secret not found: {args.name}")
        return EXIT_ERROR
    print_error("Unknown secret command")
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
