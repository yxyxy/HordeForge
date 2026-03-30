import argparse
import asyncio
import json
import os
import sys

# =============================================================================
# Token Budget System (full implementations for CLI)
# =============================================================================
from typing import Any

from agents.llm_api import (
    ApiConfiguration,
    ApiProvider,
    LlmApi,
    LlmRouter,
    create_ollama_api,
)
from agents.llm_wrapper import ApiStreamTextChunk, ApiStreamToolCallsChunk, ApiStreamUsageChunk

# Import BudgetLimits for CLI usage
from agents.token_budget_system import BudgetLimits
from agents.token_budget_system import BudgetLimits as TokenBudgetLimits
from agents.token_budget_system import get_usage_summary as get_token_usage_summary
from agents.token_budget_system import set_budget_limits as set_token_budget_limits


def get_usage_summary() -> dict[str, Any]:
    """Get current token usage summary."""
    return get_token_usage_summary()


def set_budget_limits(limits: TokenBudgetLimits) -> None:
    """Set budget limits for token usage."""
    set_token_budget_limits(limits)


class LlmCli:
    """Command Line Interface for LLM API operations."""

    def __init__(self):
        self.router = LlmRouter()
        self.current_api: LlmApi | None = None

    def setup_parser(self) -> argparse.ArgumentParser:
        """Setup command line argument parser."""
        parser = argparse.ArgumentParser(description="LLM API Command Line Interface")

        # Global options
        parser.add_argument(
            "--provider", choices=[p.value for p in ApiProvider], help="LLM provider to use"
        )
        parser.add_argument("--model", type=str, help="Model name to use")
        parser.add_argument("--api-key", type=str, help="API key for the provider")
        parser.add_argument("--base-url", type=str, help="Base URL for local providers")
        parser.add_argument("--region", type=str, help="Region for cloud providers")
        parser.add_argument("--project-id", type=str, help="Project ID for Vertex AI")
        parser.add_argument("--plan", action="store_true", help="Plan mode - analyze and plan")
        parser.add_argument("--act", action="store_true", help="Act mode - execute actions")
        parser.add_argument("--settings", action="store_true", help="Open settings configuration")

        # Subcommands
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Chat command
        chat_parser = subparsers.add_parser("chat", help="Interactive chat with LLM")
        chat_parser.add_argument("--system", type=str, help="System prompt")
        chat_parser.add_argument("--file", type=str, help="File containing the prompt")

        # Plan command
        plan_parser = subparsers.add_parser("plan", help="Plan mode - analyze and plan")
        plan_parser.add_argument("prompt", nargs="*", help="Prompt to analyze")
        plan_parser.add_argument("--plan", action="store_true", help="Alias for plan mode")

        # Act command
        act_parser = subparsers.add_parser("act", help="Act mode - execute actions")
        act_parser.add_argument("prompt", nargs="*", help="Prompt to execute")
        act_parser.add_argument("--act", action="store_true", help="Alias for act mode")

        # Test command
        subparsers.add_parser("test", help="Test provider connectivity")

        # LLM command (alias for default prompt mode)
        llm_parser = subparsers.add_parser("llm", help="Send a prompt to LLM")
        llm_parser.add_argument("prompt", nargs="*", help="Prompt to send to LLM")

        # List providers command
        subparsers.add_parser("list-providers", help="List available providers")

        # Settings command
        settings_parser = subparsers.add_parser("settings", help="Manage provider settings")
        settings_parser.add_argument("--save", action="store_true", help="Save current settings")
        settings_parser.add_argument("--load", action="store_true", help="Load saved settings")
        settings_parser.add_argument("--validate", action="store_true", help="Validate API keys")
        settings_parser.add_argument("--profile", type=str, help="Profile name to use")
        settings_parser.add_argument(
            "--list-profiles", action="store_true", help="List all profiles"
        )
        settings_parser.add_argument("--delete-profile", type=str, help="Delete profile")
        settings_parser.add_argument("--switch-profile", type=str, help="Switch to profile")
        settings_parser.add_argument("--export-profile", type=str, help="Export profile to file")
        settings_parser.add_argument("--import-profile", type=str, help="Import profile from file")

        # Tokens/Cost tracking
        tokens_parser = subparsers.add_parser("tokens", help="Show token usage")
        tokens_parser.add_argument("--history", action="store_true", help="Show usage history")
        subparsers.add_parser("cost", help="Show cost information")
        budget_parser = subparsers.add_parser("budget", help="Show budget information")
        budget_parser.add_argument("--set-daily", type=float, help="Set daily budget limit")
        budget_parser.add_argument("--set-monthly", type=float, help="Set monthly budget limit")
        budget_parser.add_argument("--set-session", type=float, help="Set session budget limit")

        return parser

    def load_settings(self, profile: str = "default") -> dict:
        """Load saved settings from file."""
        if profile == "default":
            settings_file = os.path.expanduser("~/.hordeforge/llm_settings.json")
        else:
            settings_file = os.path.expanduser(f"~/.hordeforge/profiles/{profile}.json")
        if os.path.exists(settings_file):
            with open(settings_file) as f:
                return json.load(f)
        return {}

    def save_settings(self, settings: dict, profile: str = "default"):
        """Save settings to file."""
        os.makedirs(os.path.expanduser("~/.hordeforge/profiles"), exist_ok=True)
        if profile == "default":
            settings_file = os.path.expanduser("~/.hordeforge/llm_settings.json")
        else:
            settings_file = os.path.expanduser(f"~/.hordeforge/profiles/{profile}.json")
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)

    def list_profiles(self) -> list[str]:
        """List all available profiles."""
        profiles_dir = os.path.expanduser("~/.hordeforge/profiles")
        if not os.path.exists(profiles_dir):
            return ["default"]
        profiles = ["default"]  # Always include default
        for filename in os.listdir(profiles_dir):
            if filename.endswith(".json"):
                profile_name = filename[:-5]  # Remove .json extension
                if profile_name != "default":  # Don't duplicate default
                    profiles.append(profile_name)
        return profiles

    def delete_profile(self, profile: str) -> bool:
        """Delete a profile."""
        if profile == "default":
            print("Cannot delete default profile")
            return False
        profile_file = os.path.expanduser(f"~/.hordeforge/profiles/{profile}.json")
        if os.path.exists(profile_file):
            os.remove(profile_file)
            return True
        return False

    def create_api_from_args(self, args) -> LlmApi:
        """Create LLM API instance from command line arguments."""
        if args.provider:
            provider = ApiProvider(args.provider)
            api_key = args.api_key or os.getenv(f"{provider.value.upper()}_API_KEY")

            config = ApiConfiguration(
                provider=provider,
                model=args.model or self._get_default_model(provider),
                api_key=api_key,
                base_url=args.base_url,
                region=args.region,
                project_id=args.project_id,
            )

            # Handle AWS credentials
            if provider == ApiProvider.BEDROCK:
                config.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
                config.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
                config.aws_session_token = os.getenv("AWS_SESSION_TOKEN")

            return LlmApi(config)
        else:
            # Try to use environment variables or defaults
            for provider in [ApiProvider.OPENAI, ApiProvider.ANTHROPIC, ApiProvider.GOOGLE]:
                api_key = os.getenv(f"{provider.value.upper()}_API_KEY")
                if api_key:
                    config = ApiConfiguration(
                        provider=provider,
                        model=self._get_default_model(provider),
                        api_key=api_key,
                    )
                    return LlmApi(config)

            # Default to Ollama if no API keys found
            return create_ollama_api()

    def _get_default_model(self, provider: ApiProvider) -> str:
        """Get default model for provider."""
        defaults = {
            ApiProvider.OPENAI: "gpt-4o",
            ApiProvider.ANTHROPIC: "claude-sonnet-4-20250514",
            ApiProvider.GOOGLE: "gemini-2.0-flash",
            ApiProvider.OLLAMA: "llama2",
            ApiProvider.GEMINI: "gemini-pro",
            ApiProvider.OPENROUTER: "openai/gpt-4o",
            ApiProvider.BEDROCK: "anthropic.claude-sonnet-4-5-20250929-v1:0",
            ApiProvider.VERTEX: "gemini-1.5-pro-001",
            ApiProvider.LMSTUDIO: "local-model",
            ApiProvider.DEEPSEEK: "deepseek-chat",
            ApiProvider.FIREWORKS: "accounts/fireworks/models/llama-v3p1-70b-instruct",
            ApiProvider.TOGETHER: "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            ApiProvider.QWEN: "qwen-max",
            ApiProvider.QWEN_CODE: "qwen3-coder-plus",
            ApiProvider.MISTRAL: "mistral-large-latest",
            ApiProvider.HUGGINGFACE: "microsoft/DialoGPT-medium",
            ApiProvider.LITELLM: "gpt-3.5-turbo",
            ApiProvider.MOONSHOT: "moonshot-v1-8k",
            ApiProvider.GROQ: "llama3-70b-8192",
        }
        return defaults.get(provider, "gpt-4o")

    async def chat_interactive(self, api: LlmApi, system_prompt: str = ""):
        """Start interactive chat session."""
        print(f"Starting chat with {api.config.provider.value} - {api.config.model}")
        print("Type 'exit' or 'quit' to end the session")
        print("-" * 50)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        while True:
            try:
                user_input = input("\nYou: ").strip()
                if user_input.lower() in ["exit", "quit", "bye"]:
                    break

                if not user_input:
                    continue

                messages.append({"role": "user", "content": user_input})

                print("\nAssistant: ", end="", flush=True)

                total_tokens = 0
                async for chunk in api.create_message(system_prompt, messages):
                    if isinstance(chunk, ApiStreamTextChunk):
                        print(chunk.text, end="", flush=True)
                    elif isinstance(chunk, ApiStreamUsageChunk):
                        total_tokens += chunk.input_tokens + chunk.output_tokens

                print()  # New line after response
                messages.append({"role": "assistant", "content": ""})  # Placeholder for response

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}")
                break

    async def process_prompt(self, api: LlmApi, system_prompt: str, user_prompt: str):
        """Process a single prompt."""
        messages = [{"role": "user", "content": user_prompt}]

        print(f"Using {api.config.provider.value} - {api.config.model}")
        print("Response:")
        print("-" * 30)

        total_input_tokens = 0
        total_output_tokens = 0

        async for chunk in api.create_message(system_prompt, messages):
            if isinstance(chunk, ApiStreamTextChunk):
                print(chunk.text, end="", flush=True)
            elif isinstance(chunk, ApiStreamUsageChunk):
                total_input_tokens += chunk.input_tokens
                total_output_tokens += chunk.output_tokens
            elif isinstance(chunk, ApiStreamToolCallsChunk):
                print(f"\n[Tool Call: {chunk.tool_call}]")

        print()  # New line
        print(f"\nTokens: Input={total_input_tokens}, Output={total_output_tokens}")

    async def test_provider(self, api: LlmApi):
        """Test provider connectivity."""
        print(f"Testing {api.config.provider.value} - {api.config.model}...")

        try:
            # Send a simple test prompt
            messages = [{"role": "user", "content": "Hello, are you working?"}]

            response_parts = []
            async for chunk in api.create_message("", messages):
                if isinstance(chunk, ApiStreamTextChunk):
                    response_parts.append(chunk.text)
                elif isinstance(chunk, ApiStreamUsageChunk):
                    print(f"  Tokens: {chunk.input_tokens} input, {chunk.output_tokens} output")

            response = "".join(response_parts)
            if response:
                print(f"[OK] Success! Response: {response[:50]}...")
            else:
                print("[OK] Success! (empty response)")

        except Exception as e:
            print(f"[FAIL] Failed: {e}")

    async def run_command(self, args):
        """Execute the specified command."""
        # Handle global --settings flag first
        if args.settings:
            print("Settings mode - managing provider configurations")
            print("Available profiles:", self.list_profiles())
            # For now, just show current settings
            current_settings = self.load_settings()
            print("Current settings:", current_settings)
            return

        # Handle global --plan and --act flags when no subcommand is provided
        if (args.plan or args.act) and not args.command:
            # Create API instance
            api = self.create_api_from_args(args)
            if args.plan:
                system_prompt = (
                    "You are a planning assistant. Analyze the request and create a detailed plan."
                )
            else:
                system_prompt = "You are an execution assistant. Take action based on the request."

            # Get user prompt from remaining args or input
            # Find the position of --plan or --act in the original sys.argv
            original_argv = sys.argv
            prompt_start_idx = -1
            for i, arg in enumerate(original_argv):
                if (args.plan and arg == "--plan") or (args.act and arg == "--act"):
                    prompt_start_idx = i + 1
                    break

            if prompt_start_idx > 0 and prompt_start_idx < len(original_argv):
                user_prompt = " ".join(original_argv[prompt_start_idx:])
            else:
                user_prompt = input("Enter your request: ")
            await self.process_prompt(api, system_prompt, user_prompt)
            return

        if args.command == "list-providers":
            print("Available providers:")
            for provider in ApiProvider:
                print(f"  - {provider.value}")
            return

        # Handle settings subcommand
        if args.command == "settings":
            if args.list_profiles:
                profiles = self.list_profiles()
                print("Available profiles:")
                for profile in profiles:
                    print(f"  - {profile}")
            elif args.delete_profile:
                if self.delete_profile(args.delete_profile):
                    print(f"Profile '{args.delete_profile}' deleted")
                else:
                    print(f"Failed to delete profile '{args.delete_profile}'")
            elif args.switch_profile:
                # Switch to profile by loading its settings
                settings = self.load_settings(args.switch_profile)
                if settings:
                    print(f"Switched to profile '{args.switch_profile}'")
                    print(f"Settings: {settings}")
                else:
                    print(f"Profile '{args.switch_profile}' not found")
            elif args.export_profile:
                settings = self.load_settings(args.export_profile)
                if settings:
                    export_file = f"./{args.export_profile}_settings.json"
                    with open(export_file, "w") as f:
                        json.dump(settings, f, indent=2)
                    print(f"Profile '{args.export_profile}' exported to {export_file}")
                else:
                    print(f"Profile '{args.export_profile}' not found")
            elif args.import_profile:
                # Import profile from file
                import_file = args.import_profile
                if os.path.exists(import_file):
                    with open(import_file) as f:
                        settings = json.load(f)
                    profile_name = (
                        os.path.basename(import_file)
                        .replace("_settings.json", "")
                        .replace(".json", "")
                    )
                    self.save_settings(settings, profile_name)
                    print(f"Profile '{profile_name}' imported from {import_file}")
                else:
                    print(f"File '{import_file}' not found")
            elif args.validate:
                # Validate API keys by testing connection
                api = self.create_api_from_args(args)
                await self.test_provider(api)
            elif args.save:
                settings = {
                    "provider": args.provider,
                    "model": args.model,
                    "base_url": args.base_url,
                    "region": args.region,
                    "project_id": args.project_id,
                }
                profile = args.profile or "default"
                self.save_settings(settings, profile)
                print(f"Settings saved for profile '{profile}'!")
            elif args.load:
                profile = args.profile or "default"
                settings = self.load_settings(profile)
                print(f"Loaded settings for profile '{profile}': {settings}")
            else:
                print("Use --save, --load, --list-profiles, --validate, or other settings options")
            return

        # Create API instance for other commands
        api = self.create_api_from_args(args)

        if args.command == "test":
            await self.test_provider(api)
        elif args.command == "chat":
            system_prompt = args.system or ""
            if args.file:
                with open(args.file) as f:
                    system_prompt = f.read()
            await self.chat_interactive(api, system_prompt)
        elif args.command in ["plan", "act", "llm"]:
            if args.command == "plan":
                system_prompt = (
                    "You are a planning assistant. Analyze the request and create a detailed plan."
                )
            elif args.command == "act":
                system_prompt = "You are an execution assistant. Take action based on the request."
            else:
                system_prompt = ""

            user_prompt = " ".join(args.prompt) if args.prompt else input("Enter your request: ")
            await self.process_prompt(api, system_prompt, user_prompt)
        elif args.command == "tokens":
            summary = get_usage_summary()
            if args.history:
                print("Usage History:")
                print(json.dumps(summary, indent=2))
            else:
                print("Current Token Usage:")
                print(f"Today: {summary.get('today', {})}")
                print(f"This Month: {summary.get('this_month', {})}")
                print(f"Session: {summary.get('session', {})}")
        elif args.command == "cost":
            summary = get_usage_summary()
            print(f"Total Cost: ${summary.get('total_cost', 0):.4f}")
        elif args.command == "budget":
            if args.set_daily:
                limits = BudgetLimits(dailyLimit=args.set_daily)
                set_budget_limits(limits)
                print(f"Daily budget set to ${args.set_daily}")
            elif args.set_monthly:
                limits = BudgetLimits(monthlyLimit=args.set_monthly)
                set_budget_limits(limits)
                print(f"Monthly budget set to ${args.set_monthly}")
            elif args.set_session:
                limits = BudgetLimits(sessionLimit=args.set_session)
                set_budget_limits(limits)
                print(f"Session budget set to ${args.set_session}")
            else:
                summary = get_usage_summary()
                print("Budget Information:")
                limits = summary.get("budget_limits", {})
                print(f"Daily Limit: ${limits.get('daily', 'Not set')}")
                print(f"Monthly Limit: ${limits.get('monthly', 'Not set')}")
                print(f"Session Limit: ${limits.get('session', 'Not set')}")
                print(f"Current Total Cost: ${summary.get('total_cost', 0):.4f}")


async def main():
    """Main entry point."""
    cli = LlmCli()
    parser = cli.setup_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()
    await cli.run_command(args)


if __name__ == "__main__":
    asyncio.run(main())
