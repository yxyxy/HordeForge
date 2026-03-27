#!/usr/bin/env python3
"""
Test script to verify all Cline providers are properly integrated in HordeForge.
"""

import asyncio

from agents.llm_api import ApiConfiguration, ApiProvider, LlmApi
from agents.llm_providers import (
    AwsBedrockHandler,
    ClaudeCodeHandler,
    DeepSeekHandler,
    FireworksHandler,
    GeminiHandler,
    GroqHandler,
    HuggingFaceHandler,
    LiteLlmHandler,
    LmStudioHandler,
    MistralHandler,
    MoonshotHandler,
    OllamaHandler,
    OpenRouterHandler,
    QwenHandler,
    TogetherHandler,
    VertexHandler,
)


async def run_comprehensive_tests():
    """Run comprehensive tests for all providers."""
    print("Testing Cline Provider Integration in HordeForge")
    print("=" * 60)

    # Test configurations for each provider
    test_configs: dict[ApiProvider, ApiConfiguration | None] = {
        # Local providers (don't need API keys)
        ApiProvider.OLLAMA: ApiConfiguration(
            provider=ApiProvider.OLLAMA, model="llama2", base_url="http://localhost:11434"
        ),
        ApiProvider.LMSTUDIO: ApiConfiguration(
            provider=ApiProvider.LMSTUDIO, model="local-model", base_url="http://localhost:1234"
        ),
        # Claude Code (special case - CLI tool)
        ApiProvider.CLAUDE_CODE: ApiConfiguration(
            provider=ApiProvider.CLAUDE_CODE, model="claude-sonnet-4-20250514", base_url=None
        ),
        # Cloud providers (will test initialization only)
        ApiProvider.GEMINI: ApiConfiguration(
            provider=ApiProvider.GEMINI,
            model="gemini-pro",
        ),
        ApiProvider.OPENROUTER: ApiConfiguration(
            provider=ApiProvider.OPENROUTER,
            model="openai/gpt-4o",
        ),
        ApiProvider.DEEPSEEK: ApiConfiguration(
            provider=ApiProvider.DEEPSEEK,
            model="deepseek-chat",
        ),
        ApiProvider.FIREWORKS: ApiConfiguration(
            provider=ApiProvider.FIREWORKS,
            model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        ),
        ApiProvider.TOGETHER: ApiConfiguration(
            provider=ApiProvider.TOGETHER,
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        ),
        ApiProvider.QWEN: ApiConfiguration(
            provider=ApiProvider.QWEN,
            model="qwen-max",
        ),
        ApiProvider.MISTRAL: ApiConfiguration(
            provider=ApiProvider.MISTRAL,
            model="mistral-large-latest",
        ),
        ApiProvider.HUGGINGFACE: ApiConfiguration(
            provider=ApiProvider.HUGGINGFACE,
            model="microsoft/DialoGPT-medium",
        ),
        ApiProvider.MOONSHOT: ApiConfiguration(
            provider=ApiProvider.MOONSHOT,
            model="moonshot-v1-8k",
        ),
        ApiProvider.GROQ: ApiConfiguration(
            provider=ApiProvider.GROQ,
            model="llama3-70b-8192",
        ),
        ApiProvider.BEDROCK: ApiConfiguration(
            provider=ApiProvider.BEDROCK,
            model="anthropic.claude-sonnet-4-5-20250929-v1:0",
        ),
        ApiProvider.VERTEX: ApiConfiguration(
            provider=ApiProvider.VERTEX,
            model="gemini-1.5-pro-001",
        ),
    }

    results = {}

    for provider_enum, config in test_configs.items():
        try:
            success = await run_single_provider(provider_enum, config)
            results[provider_enum.value] = success
        except Exception as e:
            print(f"  ❌ Test failed completely: {e}")
            results[provider_enum.value] = False

    # Print summary
    print(f"\n{'=' * 60}")
    print("TEST SUMMARY")
    print(f"{'=' * 60}")

    passed = sum(1 for success in results.values() if success)
    total = len(results)

    for provider, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{provider:20}: {status}")

    print(f"\nOverall: {passed}/{total} providers working")

    if passed == total:
        print("🎉 All Cline providers successfully integrated!")
        return True
    else:
        print(f"⚠️ {total - passed} providers need attention")
        return False


async def run_single_provider(provider_enum: ApiProvider, config: ApiConfiguration):
    """Test a single provider with basic functionality."""
    provider_name = provider_enum.value

    print(f"\n{'=' * 50}")
    print(f"Testing {provider_name}")
    print(f"{'=' * 50}")

    try:
        llm_api = LlmApi(config)

        # Test model info
        model_success = await run_provider_model_info(provider_name, llm_api)

        # Test streaming (only if API key is available)
        await run_provider_streaming(provider_name, llm_api)

        success = model_success  # Don't require streaming for test to pass (may need API keys)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{provider_name}: {status}")

        return success

    except Exception as e:
        print(f"  ❌ Provider initialization failed: {e}")
        return False


async def run_provider_streaming(provider_name: str, llm_api):
    """Test streaming functionality for a provider."""
    print(f"\nTesting {provider_name} streaming...")

    try:
        # Simple test message
        system_prompt = "You are a helpful assistant. Respond briefly."
        messages = [{"role": "user", "content": "Hello, test message!"}]

        response_chunks = []
        async for chunk in llm_api.create_message(system_prompt, messages):
            if hasattr(chunk, "text") and chunk.text:
                response_chunks.append(chunk.text)
                print(f"  Received chunk: {chunk.text[:50]}...")
                if len(response_chunks) >= 3:  # Limit for testing
                    break

        response = "".join(response_chunks)
        print(f"  Final response length: {len(response)} chars")
        return True

    except Exception as e:
        print(f"  ❌ Streaming test failed: {e}")
        return False


async def run_provider_model_info(provider_name: str, llm_api):
    """Test model information retrieval."""
    print(f"Testing {provider_name} model info...")

    try:
        model_id, model_info = llm_api.get_model_info()
        print(f"  Model ID: {model_id}")
        print(f"  Context window: {model_info.context_window}")
        print(f"  Supports images: {model_info.supports_images}")
        print(f"  Supports reasoning: {model_info.supports_reasoning}")
        return True

    except Exception as e:
        print(f"  ❌ Model info test failed: {e}")
        return False


async def run_handler_directly():
    """Test handlers directly to ensure they're properly implemented."""
    print("\nTesting handlers directly...")

    handlers_to_test = [
        ("OllamaHandler", lambda: OllamaHandler()),
        ("ClaudeCodeHandler", lambda: ClaudeCodeHandler()),
        ("GeminiHandler", lambda: GeminiHandler(gemini_api_key="fake-key")),
        ("OpenRouterHandler", lambda: OpenRouterHandler(openrouter_api_key="fake-key")),
        (
            "AwsBedrockHandler",
            lambda: AwsBedrockHandler(aws_access_key="fake-key", aws_secret_key="fake-secret"),
        ),
        ("VertexHandler", lambda: VertexHandler(vertex_project_id="fake-project")),
        ("LmStudioHandler", lambda: LmStudioHandler()),
        ("DeepSeekHandler", lambda: DeepSeekHandler(deepseek_api_key="fake-key")),
        ("FireworksHandler", lambda: FireworksHandler(fireworks_api_key="fake-key")),
        ("TogetherHandler", lambda: TogetherHandler(together_api_key="fake-key")),
        ("QwenHandler", lambda: QwenHandler(qwen_api_key="fake-key")),
        ("MistralHandler", lambda: MistralHandler(mistral_api_key="fake-key")),
        ("HuggingFaceHandler", lambda: HuggingFaceHandler(huggingface_api_key="fake-key")),
        ("LiteLlmHandler", lambda: LiteLlmHandler()),
        ("MoonshotHandler", lambda: MoonshotHandler(moonshot_api_key="fake-key")),
        ("GroqHandler", lambda: GroqHandler(groq_api_key="fake-key")),
    ]

    handler_results = {}

    for handler_name, handler_constructor in handlers_to_test:
        try:
            handler = handler_constructor()
            model_id, model_info = handler.get_model()
            print(f"  {handler_name}: ✅ Model={model_id}, Context={model_info.context_window}")
            handler_results[handler_name] = True
        except Exception as e:
            print(f"  {handler_name}: ❌ {e}")
            handler_results[handler_name] = False

    return all(handler_results.values())


if __name__ == "__main__":
    print("Starting Cline Provider Integration Tests...")

    # Test handlers directly first
    handlers_ok = asyncio.run(run_handler_directly())

    # Test full integration
    integration_ok = asyncio.run(run_comprehensive_tests())

    if handlers_ok and integration_ok:
        print("\n🎉 All tests passed! Cline provider integration is complete.")
        exit(0)
    else:
        print("\n❌ Some tests failed. Check the output above.")
        exit(1)
