#!/usr/bin/env python3
"""Validation tests for provider integration in HordeForge."""

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
    """All handlers should implement the ApiHandler interface contract."""
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

    failures: list[str] = []
    for handler_name, handler_class in handlers:
        if not issubclass(handler_class, ApiHandler):
            failures.append(f"{handler_name}: does not inherit from ApiHandler")
            continue

        for method_name in ("create_message", "get_model", "get_api_stream_usage", "abort"):
            if not hasattr(handler_class, method_name):
                failures.append(f"{handler_name}: missing method {method_name}")
                continue
            if method_name == "create_message":
                param_names = list(
                    inspect.signature(getattr(handler_class, method_name)).parameters
                )
                if not all(param in param_names for param in ("system_prompt", "messages")):
                    failures.append(f"{handler_name}: create_message missing required parameters")

    assert not failures, " ; ".join(failures)


def test_api_provider_enum():
    """Expected providers should be present in ApiProvider enum."""
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
    assert not missing, f"Missing providers: {sorted(missing)}"


def test_handler_instantiation():
    """Handlers should instantiate with minimal config."""
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

    tolerated_tokens = ("API_KEY", "credentials", "project", "max_tokens")
    failures: list[str] = []
    for handler_class, kwargs in test_cases:
        try:
            handler = handler_class(**kwargs)
            handler.get_model()
        except Exception as exc:  # noqa: BLE001
            if not any(token in str(exc) for token in tolerated_tokens):
                failures.append(f"{handler_class.__name__}: {exc}")

    assert not failures, " ; ".join(failures)


def test_api_configuration_handling():
    """LlmApi should build handlers for all provider configs."""
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

    tolerated_tokens = ("API_KEY", "credentials", "project", "max_tokens")
    failures: list[str] = []
    for config in configs:
        try:
            api_instance = LlmApi(config)
            api_instance.get_model_info()
        except Exception as exc:  # noqa: BLE001
            if not any(token in str(exc) for token in tolerated_tokens):
                failures.append(f"{config.provider.value}: {exc}")

    assert not failures, " ; ".join(failures)


def test_streaming_types():
    """Streaming chunk types should be constructible."""
    from agents.llm_wrapper import (
        ApiStreamTextChunk,
        ApiStreamThinkingChunk,
        ApiStreamToolCallsChunk,
        ApiStreamUsageChunk,
    )

    text_chunk = ApiStreamTextChunk(text="test")
    usage_chunk = ApiStreamUsageChunk(input_tokens=10, output_tokens=5)
    tool_chunk = ApiStreamToolCallsChunk(tool_call={"test": "data"})
    thinking_chunk = ApiStreamThinkingChunk(reasoning="thinking")

    assert text_chunk.text == "test"
    assert usage_chunk.input_tokens == 10
    assert usage_chunk.output_tokens == 5
    assert tool_chunk.tool_call == {"test": "data"}
    assert thinking_chunk.reasoning == "thinking"


async def run_validation_tests() -> bool:
    """Run validation tests in script mode."""
    tests = [
        test_handler_interface_compliance,
        test_api_provider_enum,
        test_handler_instantiation,
        test_api_configuration_handling,
        test_streaming_types,
    ]
    passed = 0
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception:  # noqa: BLE001
            pass
    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(run_validation_tests())
    raise SystemExit(0 if success else 1)
