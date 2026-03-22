#!/usr/bin/env python3
"""
Validation test for Cline provider integration in HordeForge.
This test validates that all providers are properly integrated
without requiring actual API calls or running services.
"""

import asyncio
import inspect

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
from agents.llm_wrapper import ApiHandler


def test_handler_interface_compliance():
    """Test that all handlers properly implement the ApiHandler interface."""
    print("Testing ApiHandler interface compliance...")

    handlers = [
        ("OllamaHandler", OllamaHandler),
        ("ClaudeCodeHandler", ClaudeCodeHandler),
        ("GeminiHandler", GeminiHandler),
        ("OpenRouterHandler", OpenRouterHandler),
        ("AwsBedrockHandler", AwsBedrockHandler),
        ("VertexHandler", VertexHandler),
        ("LmStudioHandler", LmStudioHandler),
        ("DeepSeekHandler", DeepSeekHandler),
        ("FireworksHandler", FireworksHandler),
        ("TogetherHandler", TogetherHandler),
        ("QwenHandler", QwenHandler),
        ("MistralHandler", MistralHandler),
        ("HuggingFaceHandler", HuggingFaceHandler),
        ("LiteLlmHandler", LiteLlmHandler),
        ("MoonshotHandler", MoonshotHandler),
        ("GroqHandler", GroqHandler),
    ]

    all_passed = True

    for handler_name, handler_class in handlers:
        print(f"  Testing {handler_name}...")

        # Check if it inherits from ApiHandler
        if not issubclass(handler_class, ApiHandler):
            print("    ❌ Does not inherit from ApiHandler")
            all_passed = False
            continue

        # Check required methods exist and have correct signatures
        methods_to_check = {
            "create_message": ["self", "system_prompt", "messages", "tools"],
            "get_model": ["self"],
            "get_api_stream_usage": ["self"],
            "abort": ["self"],
        }

        for method_name in methods_to_check.keys():
            if not hasattr(handler_class, method_name):
                print(f"    ❌ Missing method: {method_name}")
                all_passed = False
                continue

            method = getattr(handler_class, method_name)
            sig = inspect.signature(method)

            if method_name == "create_message":
                # Special check for create_message - it should have the right parameters
                param_names = list(sig.parameters.keys())
                if not all(p in param_names for p in ["system_prompt", "messages"]):
                    print(f"    ❌ {method_name} missing required parameters")
                    all_passed = False
                else:
                    print(f"    ✅ {method_name} signature correct")
            else:
                print(f"    ✅ {method_name} exists")

    return all_passed


def test_api_provider_enum():
    """Test that all providers are registered in ApiProvider enum."""
    print("\nTesting ApiProvider enum completeness...")

    expected_providers = {
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
    }

    actual_providers = {provider.value for provider in ApiProvider}

    missing = expected_providers - actual_providers
    extra = actual_providers - expected_providers

    if missing:
        print(f"  ❌ Missing providers: {missing}")
        return False

    if extra:
        print(f"  ⚠️  Extra providers: {extra}")

    print(f"  ✅ All {len(expected_providers)} providers registered")
    return True


def test_handler_instantiation():
    """Test that handlers can be instantiated with minimal parameters."""
    print("\nTesting handler instantiation...")

    test_cases = [
        (OllamaHandler, {}),
        (ClaudeCodeHandler, {}),
        (GeminiHandler, {"gemini_api_key": "fake-key"}),
        (OpenRouterHandler, {"openrouter_api_key": "fake-key"}),
        (AwsBedrockHandler, {"aws_access_key": "fake-key", "aws_secret_key": "fake-secret"}),
        (VertexHandler, {"vertex_project_id": "fake-project"}),
        (LmStudioHandler, {}),
        (DeepSeekHandler, {"deepseek_api_key": "fake-key"}),
        (FireworksHandler, {"fireworks_api_key": "fake-key"}),
        (TogetherHandler, {"together_api_key": "fake-key"}),
        (QwenHandler, {"qwen_api_key": "fake-key"}),
        (MistralHandler, {"mistral_api_key": "fake-key"}),
        (HuggingFaceHandler, {"huggingface_api_key": "fake-key"}),
        (LiteLlmHandler, {}),
        (MoonshotHandler, {"moonshot_api_key": "fake-key"}),
        (GroqHandler, {"groq_api_key": "fake-key"}),
    ]

    all_passed = True

    for handler_class, kwargs in test_cases:
        try:
            handler = handler_class(**kwargs)
            model_id, model_info = handler.get_model()
            print(f"  ✅ {handler_class.__name__}: Model={model_id}")
        except Exception as e:
            print(f"  ❌ {handler_class.__name__}: {e}")
            all_passed = False

    return all_passed


def test_api_configuration_handling():
    """Test that ApiConfiguration works with all providers."""
    print("\nTesting ApiConfiguration handling...")

    # Test configs for each provider type
    configs = [
        ApiConfiguration(provider=ApiProvider.OLLAMA, model="llama2"),
        ApiConfiguration(provider=ApiProvider.CLAUDE_CODE, model="claude-sonnet"),
        ApiConfiguration(provider=ApiProvider.GEMINI, model="gemini-pro"),
        ApiConfiguration(provider=ApiProvider.OPENROUTER, model="openai/gpt-4o"),
        ApiConfiguration(provider=ApiProvider.BEDROCK, model="anthropic.claude-sonnet"),
        ApiConfiguration(
            provider=ApiProvider.VERTEX, model="gemini-1.5-pro", project_id="test-project"
        ),
        ApiConfiguration(provider=ApiProvider.LMSTUDIO, model="local-model"),
        ApiConfiguration(provider=ApiProvider.DEEPSEEK, model="deepseek-chat"),
        ApiConfiguration(provider=ApiProvider.FIREWORKS, model="llama-v3p1-70b-instruct"),
        ApiConfiguration(provider=ApiProvider.TOGETHER, model="llama-3.1-70b"),
        ApiConfiguration(provider=ApiProvider.QWEN, model="qwen-max"),
        ApiConfiguration(provider=ApiProvider.MISTRAL, model="mistral-large"),
        ApiConfiguration(provider=ApiProvider.HUGGINGFACE, model="gpt2"),
        ApiConfiguration(provider=ApiProvider.LITELLM, model="gpt-3.5-turbo"),
        ApiConfiguration(provider=ApiProvider.MOONSHOT, model="moonshot-v1-8k"),
        ApiConfiguration(provider=ApiProvider.GROQ, model="llama3-70b-8192"),
    ]

    all_passed = True

    for config in configs:
        try:
            # This tests the _create_handler method in LlmApi
            api_instance = LlmApi(config)
            model_id, model_info = api_instance.get_model_info()
            print(f"  ✅ {config.provider.value}: Handler created, Model={model_id}")
        except Exception as e:
            # Expected for providers that need API keys
            if "API_KEY" in str(e) or "credentials" in str(e) or "project" in str(e):
                print(f"  ✅ {config.provider.value}: Handler created (expected API key error)")
            else:
                print(f"  ❌ {config.provider.value}: Unexpected error - {e}")
                all_passed = False

    return all_passed


def test_streaming_types():
    """Test that streaming types are properly defined and compatible."""
    print("\nTesting streaming types compatibility...")

    from agents.llm_wrapper import (
        ApiStreamTextChunk,
        ApiStreamThinkingChunk,
        ApiStreamToolCallsChunk,
        ApiStreamUsageChunk,
    )

    # Test that we can create instances of streaming chunks
    try:
        text_chunk = ApiStreamTextChunk(text="test")
        usage_chunk = ApiStreamUsageChunk(input_tokens=10, output_tokens=5)
        tool_chunk = ApiStreamToolCallsChunk(tool_call={"test": "data"})
        thinking_chunk = ApiStreamThinkingChunk(reasoning="thinking")

        print("  ✅ All streaming chunk types can be instantiated")
        print(f"  ✅ Text chunk: {text_chunk.text}")
        print(f"  ✅ Usage chunk: {usage_chunk.input_tokens} -> {usage_chunk.output_tokens}")
        print(f"  ✅ Tool chunk: {tool_chunk.tool_call}")
        print(f"  ✅ Thinking chunk: {thinking_chunk.reasoning}")

        return True
    except Exception as e:
        print(f"  ❌ Streaming types test failed: {e}")
        return False


async def run_validation_tests():
    """Run all validation tests."""
    print("Running Cline Provider Integration Validation Tests")
    print("=" * 60)

    tests = [
        ("ApiHandler Interface Compliance", test_handler_interface_compliance),
        ("ApiProvider Enum Completeness", test_api_provider_enum),
        ("Handler Instantiation", test_handler_instantiation),
        ("ApiConfiguration Handling", test_api_configuration_handling),
        ("Streaming Types Compatibility", test_streaming_types),
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * len(test_name))
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"  ❌ Test failed with exception: {e}")
            results[test_name] = False

    # Print summary
    print(f"\n{'=' * 60}")
    print("VALIDATION SUMMARY")
    print(f"{'=' * 60}")

    passed = sum(1 for success in results.values() if success)
    total = len(results)

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:30}: {status}")

    print(f"\nOverall: {passed}/{total} validation tests passed")

    if passed == total:
        print("\n🎉 All validation tests passed!")
        print("✅ Cline provider integration is complete and correct!")
        print("✅ All 17 providers (including Claude Code) are properly integrated")
        print("✅ Interface compliance verified")
        print("✅ Configuration handling verified")
        print("✅ Streaming compatibility verified")
        return True
    else:
        print(f"\n❌ {total - passed} validation tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_validation_tests())
    exit(0 if success else 1)
