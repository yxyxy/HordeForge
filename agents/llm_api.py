from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .llm_providers import (
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
    QwenCodeHandler,
    QwenHandler,
    TogetherHandler,
    VertexHandler,
)
from .llm_wrapper import (
    ApiHandler,
    ApiStreamChunk,
    ApiStreamTextChunk,  # noqa: F401 - Exported for backward compatibility
    ApiStreamThinkingChunk,  # noqa: F401 - Exported for backward compatibility
    ApiStreamToolCallsChunk,  # noqa: F401 - Exported for backward compatibility
    ApiStreamUsageChunk,  # noqa: F401 - Exported for backward compatibility
    LLMResponse,  # noqa: F401 - Exported for backward compatibility
    LLMRouter,  # noqa: F401 - Exported for backward compatibility
    LLMWrapper,
    ModelInfo,
    build_code_prompt,  # noqa: F401 - Exported for backward compatibility
    build_code_review_prompt,  # noqa: F401 - Exported for backward compatibility
    build_spec_prompt,  # noqa: F401 - Exported for backward compatibility
    detect_language,  # noqa: F401 - Exported for backward compatibility
    detect_spec_type,  # noqa: F401 - Exported for backward compatibility
    generate_code_with_retry,  # noqa: F401 - Exported for backward compatibility
    generate_spec_with_retry,  # noqa: F401 - Exported for backward compatibility
    get_llm_wrapper,
    parse_code_output,  # noqa: F401 - Exported for backward compatibility
    parse_review_output,  # noqa: F401 - Exported for backward compatibility
    parse_spec_output,  # noqa: F401 - Exported for backward compatibility
)

logger = logging.getLogger(__name__)

# Type alias for API streams
ApiStream = AsyncGenerator[ApiStreamChunk, None]


class ApiProvider(Enum):
    """Supported API providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    BEDROCK = "bedrock"
    VERTEX = "vertex"
    LMSTUDIO = "lmstudio"
    DEEPSEEK = "deepseek"
    FIREWORKS = "fireworks"
    TOGETHER = "together"
    QWEN = "qwen"
    QWEN_CODE = "qwen-code"
    MISTRAL = "mistral"
    HUGGINGFACE = "huggingface"
    LITELLM = "litellm"
    MOONSHOT = "moonshot"
    GROQ = "groq"
    CLAUDE_CODE = "claude_code"


@dataclass
class ApiConfiguration:
    """API configuration for different providers."""

    # General settings
    provider: ApiProvider
    model: str
    api_key: str | None = None

    # Provider-specific settings
    base_url: str | None = None
    region: str | None = None
    project_id: str | None = None

    # Advanced settings
    temperature: float = 0.7
    max_tokens: int = 4000
    thinking_budget_tokens: int = 0
    reasoning_effort: str = "low"
    enable_parallel_tool_calling: bool = False

    # Credentials
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
    aws_session_token: str | None = None


class LlmApi:
    """Unified LLM API interface supporting multiple providers."""

    def __init__(self, config: ApiConfiguration):
        self.config = config
        self.handler = self._create_handler()
        # Store the underlying LLM wrapper for backward compatibility
        self._llm_wrapper = self._create_llm_wrapper()

    def _create_handler(self) -> ApiHandler:
        """Create appropriate handler based on provider."""
        if self.config.provider == ApiProvider.OPENAI:
            from .llm_wrapper import OpenAIWrapper

            return OpenAIWrapper(
                api_key=self.config.api_key,
                model=self.config.model,
            )
        elif self.config.provider == ApiProvider.ANTHROPIC:
            from .llm_wrapper import AnthropicWrapper

            return AnthropicWrapper(
                api_key=self.config.api_key,
                model=self.config.model,
            )
        elif self.config.provider == ApiProvider.GOOGLE:
            from .llm_wrapper import GoogleGenAIWrapper

            return GoogleGenAIWrapper(
                api_key=self.config.api_key,
                model=self.config.model,
            )
        elif self.config.provider == ApiProvider.OLLAMA:
            return OllamaHandler(
                ollama_base_url=self.config.base_url,
                ollama_api_key=self.config.api_key,
                ollama_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.GEMINI:
            return GeminiHandler(
                gemini_api_key=self.config.api_key,
                gemini_model_id=self.config.model,
                gemini_base_url=self.config.base_url,
                thinking_budget_tokens=self.config.thinking_budget_tokens,
                reasoning_effort=self.config.reasoning_effort,
            )
        elif self.config.provider == ApiProvider.OPENROUTER:
            return OpenRouterHandler(
                openrouter_api_key=self.config.api_key,
                openrouter_model_id=self.config.model,
                reasoning_effort=self.config.reasoning_effort,
                thinking_budget_tokens=self.config.thinking_budget_tokens,
                enable_parallel_tool_calling=self.config.enable_parallel_tool_calling,
            )
        elif self.config.provider == ApiProvider.BEDROCK:
            return AwsBedrockHandler(
                aws_access_key=self.config.aws_access_key,
                aws_secret_key=self.config.aws_secret_key,
                aws_region=self.config.region or "us-east-1",
                aws_session_token=self.config.aws_session_token,
                aws_bedrock_model_id=self.config.model,
                thinking_budget_tokens=self.config.thinking_budget_tokens,
            )
        elif self.config.provider == ApiProvider.VERTEX:
            return VertexHandler(
                vertex_project_id=self.config.project_id or os.getenv("VERTEX_PROJECT_ID"),
                vertex_region=self.config.region or os.getenv("VERTEX_REGION", "us-central1"),
                vertex_api_key=self.config.api_key,
                vertex_model_id=self.config.model,
                thinking_budget_tokens=self.config.thinking_budget_tokens,
            )
        elif self.config.provider == ApiProvider.LMSTUDIO:
            return LmStudioHandler(
                lmstudio_base_url=self.config.base_url,
                lmstudio_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.DEEPSEEK:
            return DeepSeekHandler(
                deepseek_api_key=self.config.api_key,
                deepseek_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.FIREWORKS:
            return FireworksHandler(
                fireworks_api_key=self.config.api_key,
                fireworks_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.TOGETHER:
            return TogetherHandler(
                together_api_key=self.config.api_key,
                together_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.QWEN:
            return QwenHandler(
                qwen_api_key=self.config.api_key,
                qwen_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.QWEN_CODE:
            return QwenCodeHandler(
                qwen_oauth_credentials_json=self.config.api_key,
                qwen_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.MISTRAL:
            return MistralHandler(
                mistral_api_key=self.config.api_key,
                mistral_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.HUGGINGFACE:
            return HuggingFaceHandler(
                huggingface_api_key=self.config.api_key,
                huggingface_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.LITELLM:
            return LiteLlmHandler(
                litellm_api_key=self.config.api_key,
                litellm_base_url=self.config.base_url,
                litellm_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.MOONSHOT:
            return MoonshotHandler(
                moonshot_api_key=self.config.api_key,
                moonshot_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.GROQ:
            return GroqHandler(
                groq_api_key=self.config.api_key,
                groq_model_id=self.config.model,
            )
        elif self.config.provider == ApiProvider.CLAUDE_CODE:
            return ClaudeCodeHandler(
                claude_code_path=self.config.base_url,
                claude_code_model_id=self.config.model,
                thinking_budget_tokens=self.config.thinking_budget_tokens,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _create_llm_wrapper(self) -> LLMWrapper | None:
        """Create LLM wrapper for backward compatibility methods."""
        try:
            return get_llm_wrapper(
                provider=self.config.provider.value,
                api_key=self.config.api_key,
                model=self.config.model,
                timeout=30,
                max_retries=3,
            )
        except Exception:
            return None

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ):
        """Create streaming message response."""
        async for chunk in self.handler.create_message(system_prompt, messages, tools):
            yield chunk

    def get_model_info(self) -> tuple[str, ModelInfo]:
        """Get current model information."""
        return self.handler.get_model()

    def get_usage(self):
        """Get current usage information."""
        return self.handler.get_api_stream_usage()

    def abort(self):
        """Abort current request."""
        self.handler.abort()

    # Backward compatibility methods
    def complete(self, prompt: str, **kwargs) -> str:
        """Backward compatible complete method."""
        if self._llm_wrapper:
            return self._llm_wrapper.complete(prompt, **kwargs)
        else:
            # Fallback to handler if wrapper not available
            raise NotImplementedError("Complete method not available for this provider")

    def complete_stream(self, prompt: str, **kwargs):
        """Backward compatible streaming method."""
        if self._llm_wrapper:
            return self._llm_wrapper.complete_stream(prompt, **kwargs)
        else:
            # Fallback to handler if wrapper not available
            raise NotImplementedError("Complete stream method not available for this provider")

    def close(self):
        """Close the underlying LLM wrapper."""
        if self._llm_wrapper and hasattr(self._llm_wrapper, "close"):
            self._llm_wrapper.close()


class LlmRouter:
    """Route requests to optimal LLM based on task type and availability."""

    def __init__(self):
        self.providers: dict[ApiProvider, ApiConfiguration] = {}
        self.fallback_order = [
            ApiProvider.OPENAI,
            ApiProvider.ANTHROPIC,
            ApiProvider.GOOGLE,
            ApiProvider.OPENROUTER,
            ApiProvider.GEMINI,
        ]

    def register_provider(self, config: ApiConfiguration):
        """Register a provider configuration."""
        self.providers[config.provider] = config

    def route_for_task(self, task_type: str) -> LlmApi:
        """Route to optimal provider for specific task type."""
        # Define optimal providers for different task types
        task_routes = {
            "spec": [ApiProvider.GOOGLE, ApiProvider.GEMINI, ApiProvider.OPENAI],
            "code": [ApiProvider.OPENAI, ApiProvider.ANTHROPIC, ApiProvider.GEMINI],
            "analysis": [ApiProvider.ANTHROPIC, ApiProvider.OPENAI, ApiProvider.GOOGLE],
            "review": [ApiProvider.ANTHROPIC, ApiProvider.OPENAI, ApiProvider.GOOGLE],
            "refactor": [ApiProvider.OPENAI, ApiProvider.GOOGLE, ApiProvider.GEMINI],
        }

        preferred_providers = task_routes.get(task_type, self.fallback_order)

        for provider in preferred_providers:
            if provider in self.providers:
                try:
                    config = self.providers[provider]
                    return LlmApi(config)
                except Exception:
                    continue

        # Fallback to first available provider
        for provider in self.fallback_order:
            if provider in self.providers:
                try:
                    config = self.providers[provider]
                    return LlmApi(config)
                except Exception:
                    continue

        raise RuntimeError("No available providers")

    def route_for_model(self, model_name: str) -> LlmApi:
        """Route to provider that supports specific model."""
        for _provider, config in self.providers.items():
            if config.model == model_name:
                try:
                    return LlmApi(config)
                except Exception:
                    continue

        raise RuntimeError(f"No provider found for model: {model_name}")


# Convenience functions for common use cases


def create_openai_api(api_key: str, model: str = "gpt-4o") -> LlmApi:
    """Create OpenAI API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.OPENAI,
        model=model,
        api_key=api_key,
    )
    return LlmApi(config)


def create_anthropic_api(api_key: str, model: str = "claude-sonnet-4-20250514") -> LlmApi:
    """Create Anthropic API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.ANTHROPIC,
        model=model,
        api_key=api_key,
    )
    return LlmApi(config)


def create_gemini_api(api_key: str, model: str = "gemini-2.0-flash") -> LlmApi:
    """Create Gemini API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.GEMINI,
        model=model,
        api_key=api_key,
    )
    return LlmApi(config)


def create_ollama_api(base_url: str = "http://localhost:11434", model: str = "llama2") -> LlmApi:
    """Create Ollama API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.OLLAMA,
        model=model,
        base_url=base_url,
    )
    return LlmApi(config)


def create_openrouter_api(api_key: str, model: str = "openai/gpt-4o") -> LlmApi:
    """Create OpenRouter API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.OPENROUTER,
        model=model,
        api_key=api_key,
    )
    return LlmApi(config)


def create_bedrock_api(
    aws_access_key: str,
    aws_secret_key: str,
    model: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    region: str = "us-east-1",
) -> LlmApi:
    """Create AWS Bedrock API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.BEDROCK,
        model=model,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        region=region,
    )
    return LlmApi(config)


def create_vertex_api(project_id: str, api_key: str, model: str = "gemini-1.5-pro-001") -> LlmApi:
    """Create Vertex AI API instance."""
    config = ApiConfiguration(
        provider=ApiProvider.VERTEX,
        model=model,
        project_id=project_id,
        api_key=api_key,
    )
    return LlmApi(config)


def create_local_api(provider: str, base_url: str, model: str) -> LlmApi:
    """Create local API instance (Ollama, LM Studio, etc.)."""
    if provider.lower() == "ollama":
        return create_ollama_api(base_url, model)
    elif provider.lower() == "lmstudio":
        config = ApiConfiguration(
            provider=ApiProvider.LMSTUDIO,
            model=model,
            base_url=base_url,
        )
        return LlmApi(config)
    else:
        raise ValueError(f"Unsupported local provider: {provider}")


# Backward compatibility utilities
def get_legacy_api(provider: str, **kwargs) -> LlmApi:
    """Get legacy API instance for backward compatibility."""
    # Map provider names to enum values
    provider_map = {
        "openai": ApiProvider.OPENAI,
        "anthropic": ApiProvider.ANTHROPIC,
        "google": ApiProvider.GOOGLE,
        "gemini": ApiProvider.GEMINI,
        "claude": ApiProvider.ANTHROPIC,
    }
    api_provider = provider_map.get(provider.lower(), ApiProvider.OPENAI)

    config = ApiConfiguration(
        provider=api_provider,
        model=kwargs.get("model", "gpt-4o"),
        api_key=kwargs.get("api_key"),
        base_url=kwargs.get("base_url"),
    )
    return LlmApi(config)


def create_legacy_router(**kwargs) -> LlmRouter:
    """Create legacy router for backward compatibility."""
    return LlmRouter(**kwargs)
