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
    print(f"ℹ️  {message}")


def print_warning(message: str) -> None:
    print(f"⚠️  {message}", file=sys.stderr)


def print_error(message: str) -> None:
    print(f"❌ {message}", file=sys.stderr)


def print_success(message: str) -> None:
    print(f"✅ {message}")


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

    # Status command
    subparsers.add_parser("status", help="Check system status")

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
        "--inputs", type=str, default="{}", help="JSON object with pipeline inputs"
    )
    pipeline_run_parser.add_argument(
        "--repo-url", type=str, help="Repository URL (for init pipeline)"
    )
    pipeline_run_parser.add_argument("--token", type=str, help="GitHub token (for init pipeline)")

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

    return parser


def run_task_interactive(prompt: str, args) -> int:
    """Run a task in interactive mode."""
    print_info(f"Running task: {prompt}")
    print_info("This would launch an interactive UI similar to Cline...")

    # For now, simulate the task execution
    try:
        inputs = {"prompt": prompt}

        if hasattr(args, "act") and args.act:
            inputs["mode"] = "act"
        elif hasattr(args, "plan") and args.plan:
            inputs["mode"] = "plan"

        if hasattr(args, "model") and args.model:
            inputs["model"] = args.model

        result = trigger_pipeline("feature_pipeline", inputs)
        print_success("Task completed successfully!")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    except Exception as e:
        print_error(f"Task failed: {e}")
        return EXIT_ERROR


def show_history(limit: int = 10, page: int = 1) -> int:
    """Show task history."""
    print_info(f"Showing task history (limit: {limit}, page: {page})")
    print("This would show historical tasks in an interactive UI...")

    # Simulate history display
    print("Recent tasks:")
    print("- Task 1: Implement user authentication (completed)")
    print("- Task 2: Design database schema (completed)")
    print("- Task 3: Add CI/CD pipeline (running)")

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
    pipeline_name: str, inputs_str: str, repo_url: str = None, token: str = None
) -> int:
    """Run a specific pipeline."""
    try:
        inputs = json.loads(inputs_str) if inputs_str else {}

        if repo_url:
            inputs["repo_url"] = repo_url
        if token:
            inputs["github_token"] = token

        result = trigger_pipeline(pipeline_name, inputs)
        print_success(f"Pipeline '{pipeline_name}' started successfully!")
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

    if args.provider:
        llm_args_list.extend(["--provider", args.provider])
    if args.model:
        llm_args_list.extend(["--model", args.model])
    if args.api_key:
        llm_args_list.extend(["--api-key", args.api_key])
    if args.base_url:
        llm_args_list.extend(["--base-url", args.base_url])
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


def main() -> int:
    """Main entry point for the Horde CLI."""
    parser = build_main_parser()

    # Parse arguments
    args = parser.parse_args()

    # Update config if gateway URL is provided
    if args.gateway_url:
        CONFIG.gateway_url = args.gateway_url

    # Handle different commands
    if args.command == "task":
        prompt = " ".join(args.task_prompt)
        return run_task_interactive(prompt, args)

    elif args.command == "history":
        return show_history(args.limit, args.page)

    elif args.command == "config":
        return show_config()

    elif args.command == "status":
        return check_status()

    elif args.command == "health":
        health_ok = check_gateway_health()
        if health_ok:
            print_success("Gateway is healthy")
            return EXIT_OK
        else:
            print_error("Gateway is unhealthy")
            return EXIT_ERROR

    elif args.command == "pipeline":
        if args.pipeline_command == "list":
            return list_pipelines()
        elif args.pipeline_command == "run":
            return run_pipeline(args.pipeline_name, args.inputs, args.repo_url, args.token)
        else:
            parser.print_help()
            return EXIT_USAGE_ERROR

    elif args.command == "llm":
        return run_llm_command(args)

    elif args.prompt:
        # Direct prompt - run in interactive mode
        return run_task_interactive(args.prompt, args)

    else:
        # No command specified - check if there's a positional argument that should be treated as a prompt
        # For this to work, we need to re-parse to get any positional arguments
        import sys

        # Get the original command line arguments, excluding the script name
        original_args = sys.argv[1:]
        # Filter out known options to find potential prompt
        non_option_args = []
        skip_next = False
        for i, arg in enumerate(original_args):
            if skip_next:
                skip_next = False
                continue
            if arg.startswith("-"):
                # Check if this is a flag that takes an argument
                if i + 1 < len(original_args) and arg in ["-c", "--config", "--gateway-url"]:
                    skip_next = True
                continue
            # If it's not a known command, treat as potential prompt
            if arg not in [
                "task",
                "t",
                "history",
                "h",
                "config",
                "status",
                "health",
                "pipeline",
                "llm",
            ]:
                non_option_args.append(arg)

        if non_option_args:
            # Treat the first non-option argument as a prompt
            prompt = " ".join(non_option_args)
            return run_task_interactive(prompt, args)
        else:
            # No command and no prompt - show help or start interactive mode
            print_info("HordeForge CLI - Interactive Development Assistant")
            print_info("Use 'horde --help' to see available commands")
            print_info("Or run 'horde \"your task\"' to start a new task")

            # For now, start in interactive mode
            print("\nStarting interactive mode...")
            try:
                while True:
                    try:
                        prompt = input("\n📝 Enter your task (or 'quit' to exit): ").strip()
                        if prompt.lower() in ["quit", "exit", "q"]:
                            print_info("Goodbye!")
                            break
                        if prompt:
                            run_task_interactive(prompt, args)
                    except KeyboardInterrupt:
                        print("\n")
                        print_info("Goodbye!")
                        break
            except EOFError:
                print("\n")
                print_info("Goodbye!")

            return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
