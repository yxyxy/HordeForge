#!/usr/bin/env python3
"""
Test script for LLM integration functionality.
This script tests the new LLM wrapper, providers, and CLI integration.
"""

import asyncio
import os

from agents.llm_api import (
    ApiConfiguration,
    ApiProvider,
    LlmApi,
    LlmRouter,
    create_anthropic_api,
    create_gemini_api,
    create_ollama_api,
    create_openai_api,
    create_openrouter_api,
)
from agents.token_budget_system import (
    BudgetLimits,
    TokenUsage,
    get_usage_summary,
    reset_session,
    set_budget_limits,
)


async def test_basic_functionality():
    """Test basic LLM API functionality."""
    print("Testing Basic LLM Functionality...")

    # Test Ollama (local provider)
    try:
        api = create_ollama_api()
        print(f"✓ Created Ollama API: {api.config.provider.value} - {api.config.model}")

        # Test simple message
        messages = [{"role": "user", "content": "Hello, test message!"}]
        response_parts = []

        async for chunk in api.create_message("", messages):
            if hasattr(chunk, "text"):
                response_parts.append(chunk.text)

        response = "".join(response_parts)
        print(f"✓ Ollama response: {response[:50] if response else '(empty)'}...")

    except Exception as e:
        print(f"✗ Ollama test failed: {e}")

    # Test with environment variables if available
    providers_to_test = []

    if os.getenv("OPENAI_API_KEY"):
        providers_to_test.append(("OpenAI", lambda: create_openai_api(os.getenv("OPENAI_API_KEY"))))

    if os.getenv("ANTHROPIC_API_KEY"):
        providers_to_test.append(
            ("Anthropic", lambda: create_anthropic_api(os.getenv("ANTHROPIC_API_KEY")))
        )

    if os.getenv("GEMINI_API_KEY"):
        providers_to_test.append(("Gemini", lambda: create_gemini_api(os.getenv("GEMINI_API_KEY"))))

    if os.getenv("OPENROUTER_API_KEY"):
        providers_to_test.append(
            ("OpenRouter", lambda: create_openrouter_api(os.getenv("OPENROUTER_API_KEY")))
        )

    for provider_name, create_func in providers_to_test:
        try:
            api = create_func()
            print(f"✓ Created {provider_name} API")

            # Test simple message
            messages = [{"role": "user", "content": "Hello!"}]
            response_parts = []

            async for chunk in api.create_message("", messages):
                if hasattr(chunk, "text"):
                    response_parts.append(chunk.text)

            response = "".join(response_parts)
            print(f"✓ {provider_name} response: {response[:50] if response else '(empty)'}...")

        except Exception as e:
            print(f"✗ {provider_name} test failed: {e}")


async def test_token_budget_system():
    """Test token budget system functionality."""
    print("\nTesting Token Budget System...")

    # Reset session for clean test
    reset_session()

    # Test budget limits
    limits = BudgetLimits(daily_limit=10.0, monthly_limit=100.0, session_limit=1.0)
    set_budget_limits(limits)

    print("✓ Budget limits set")

    # Test usage summary
    summary = get_usage_summary()
    print(f"✓ Usage summary retrieved: {len(summary)} keys")

    # Test manual cost calculation
    from agents.llm_wrapper import ModelInfo

    # Create model info for testing purposes (not used in this test)
    ModelInfo(
        name="test-model",
        inputPrice=0.01,  # $0.01 per million tokens - используем имя в формате camelCase
        outputPrice=0.03,  # $0.03 per million tokens - используем имя в формате camelCase
        contextWindow=4096,
        maxTokens=2048,
    )

    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        cache_write_tokens=0,
        cache_read_tokens=0,
        thoughts_token_count=0,
    )

    # This would normally be called through the budget system
    print(f"✓ Manual usage test: {usage.total_tokens()} tokens")


async def test_router_functionality():
    """Test LLM router functionality."""
    print("\nTesting Router Functionality...")

    router = LlmRouter()

    # Register some providers if available
    if os.getenv("OPENAI_API_KEY"):
        config = ApiConfiguration(
            provider=ApiProvider.OPENAI, model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY")
        )
        router.register_provider(config)
        print("✓ OpenAI provider registered")

    if os.getenv("ANTHROPIC_API_KEY"):
        config = ApiConfiguration(
            provider=ApiProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        router.register_provider(config)
        print("✓ Anthropic provider registered")

    # Test routing
    try:
        api = router.route_for_task("code")
        print(f"✓ Routed for 'code' task: {api.config.provider.value}")
    except RuntimeError as e:
        print(f"⚠ No providers available for routing: {e}")

    try:
        api = router.route_for_task("analysis")
        print(f"✓ Routed for 'analysis' task: {api.config.provider.value}")
    except RuntimeError as e:
        print(f"⚠ No providers available for routing: {e}")


async def test_specific_providers():
    """Test specific provider integrations."""
    print("\nTesting Specific Provider Integrations...")

    # Test configuration creation
    configs_to_test = []

    if os.getenv("OPENAI_API_KEY"):
        configs_to_test.append(
            ApiConfiguration(
                provider=ApiProvider.OPENAI, model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY")
            )
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        configs_to_test.append(
            ApiConfiguration(
                provider=ApiProvider.ANTHROPIC,
                model="claude-sonnet-4-20250514",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
            )
        )

    if os.getenv("GEMINI_API_KEY"):
        configs_to_test.append(
            ApiConfiguration(
                provider=ApiProvider.GEMINI,
                model="gemini-2.0-flash",
                api_key=os.getenv("GEMINI_API_KEY"),
            )
        )

    for config in configs_to_test:
        try:
            api = LlmApi(config)
            print(f"✓ Created API for {config.provider.value}: {api.config.model}")

            # Test model info
            model_id, model_info = api.get_model_info()
            print(f"  Model: {model_id}, Context: {model_info.context_window}")

        except Exception as e:
            print(f"✗ {config.provider.value} API creation failed: {e}")


async def main():
    """Main test function."""
    print("LLM Integration Test Suite")
    print("=" * 50)

    await test_basic_functionality()
    await test_token_budget_system()
    await test_router_functionality()
    await test_specific_providers()

    print("\n" + "=" * 50)
    print("Test suite completed!")

    # Show final usage summary
    summary = get_usage_summary()
    print("\nFinal Usage Summary:")
    print(f"  Today: {len(summary.get('today', {}))} providers")
    print(f"  This Month: {len(summary.get('this_month', {}))} providers")
    print(f"  Session: {len(summary.get('session', {}))} providers")
    print(f"  Total Cost: ${summary.get('total_cost', 0):.4f}")


if __name__ == "__main__":
    asyncio.run(main())
