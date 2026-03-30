from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any

import anthropic
import google.genai as genai
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Default timeout for API calls (seconds)
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3


@dataclass
class TokenBudget:
    """Token budget tracking for LLM calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    max_tokens: int = 4000

    @property
    def context_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.context_tokens

    def is_within_budget(self, estimated_completion: int = 500) -> bool:
        """Check if request fits within budget."""
        return self.context_tokens + estimated_completion <= self.max_tokens


@dataclass
class LLMResponse:
    """Structured LLM response with metadata."""

    content: str
    model: str
    tokens: TokenBudget = field(default_factory=TokenBudget)
    finish_reason: str | None = None


@dataclass
class ModelInfo:
    """Model information with pricing and capabilities - Cline compatible."""

    name: str | None = None
    maxTokens: int | None = None  # Cline naming convention
    contextWindow: int | None = None  # Cline naming convention
    supportsImages: bool = False  # Cline naming convention
    supportsPromptCache: bool = False  # Cline naming convention
    supportsReasoning: bool = False  # Cline naming convention
    inputPrice: float | None = None  # Price per million tokens - Cline naming
    outputPrice: float | None = None  # Price per million tokens - Cline naming
    cacheWritesPrice: float | None = None  # Price per million tokens - Cline naming
    cacheReadsPrice: float | None = None  # Price per million tokens - Cline naming
    description: str | None = None
    temperature: float | None = None
    supportsGlobalEndpoint: bool = False  # Cline naming convention

    # Tiered pricing support - Cline compatible
    tiers: list[dict[str, Any]] | None = None

    # Reasoning configuration - Cline compatible
    thinkingConfig: dict[str, Any] | None = None

    # Backward compatibility properties
    @property
    def max_tokens(self) -> int | None:
        return self.maxTokens

    @property
    def context_window(self) -> int | None:
        return self.contextWindow

    @property
    def supports_images(self) -> bool:
        return self.supportsImages

    @property
    def supports_prompt_cache(self) -> bool:
        return self.supportsPromptCache

    @property
    def supports_reasoning(self) -> bool:
        return self.supportsReasoning

    @property
    def input_price(self) -> float | None:
        return self.inputPrice

    @property
    def output_price(self) -> float | None:
        return self.outputPrice

    @property
    def cache_writes_price(self) -> float | None:
        return self.cacheWritesPrice

    @property
    def cache_reads_price(self) -> float | None:
        return self.cacheReadsPrice

    @property
    def supports_global_endpoint(self) -> bool:
        return self.supportsGlobalEndpoint

    @property
    def thinking_config(self) -> dict[str, Any] | None:
        return self.thinkingConfig


@dataclass
class ApiStreamChunk:
    """Base class for API stream chunks."""

    type: str


@dataclass
class ApiStreamTextChunk:
    """Text content chunk from streaming response."""

    type: str = "text"
    text: str = ""
    id: str | None = None
    signature: str | None = None


@dataclass
class ApiStreamUsageChunk:
    """Usage statistics chunk from streaming response."""

    type: str = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    thoughts_token_count: int = 0
    total_cost: float | None = None
    id: str | None = None


@dataclass
class ApiStreamToolCallsChunk:
    """Tool calls chunk from streaming response."""

    type: str = "tool_calls"
    tool_call: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    signature: str | None = None


@dataclass
class ApiStreamThinkingChunk:
    """Reasoning/thinking chunk from streaming response."""

    type: str = "reasoning"
    reasoning: str = ""
    details: Any | None = None
    signature: str | None = None
    redacted_data: str | None = None
    id: str | None = None


ApiStream = AsyncGenerator[ApiStreamChunk, None]


class ApiHandler(ABC):
    """Abstract API handler interface compatible with Cline architecture."""

    @abstractmethod
    def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message response."""
        pass

    @abstractmethod
    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model ID and info."""
        pass

    @abstractmethod
    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        pass

    @abstractmethod
    def abort(self) -> None:
        """Abort current request."""
        pass


class LLMWrapper(ABC):
    """Abstract LLM wrapper for code generation."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self._api_key = api_key or self._get_api_key_from_env()
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @abstractmethod
    def _get_api_key_from_env(self) -> str:
        """Get API key from environment variables."""
        raise NotImplementedError

    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> str:
        """Generate completion from prompt."""
        raise NotImplementedError

    @abstractmethod
    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Generate streaming completion from prompt."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        raise NotImplementedError

    def _apply_retry(self, func, *args, **kwargs):
        """Apply exponential backoff retry to a function."""
        retry_config = retry(
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        return retry_config(func)(*args, **kwargs)


class OpenAIWrapper(LLMWrapper, ApiHandler):
    """OpenAI API wrapper with streaming support and Cline compatibility."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_url: str | None = None,
        env_var_name: str = "HORDEFORGE_OPENAI_API_KEY",
    ):
        self._env_var_name = env_var_name
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None
        self._current_stream = None
        self._base_url = base_url

    def _get_api_key_from_env(self) -> str:
        return os.getenv(self._env_var_name, "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                self._client = OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                    timeout=self._timeout,
                    max_retries=0,  # We handle retries ourselves
                )
            except ImportError:
                pass
        return self._client

    def complete(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError("OpenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = self._apply_retry(
                client.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=max_tokens,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}") from e

        if not response.choices or not response.choices[0].message.content:
            raise RuntimeError("Empty response from OpenAI API")

        return response.choices[0].message.content

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Streaming completion using OpenAI Chat Completions API."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("OpenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API stream failed: {e}") from e

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message with Cline-compatible interface."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("OpenAI client not available. Check API key.")

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                temperature=0.7,
                max_tokens=4000,
                stream=True,
                tools=tools,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta

                    if delta.content:
                        yield ApiStreamTextChunk(text=delta.content)

                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            yield ApiStreamToolCallsChunk(
                                tool_call={
                                    "call_id": tool_call.id,
                                    "function": {
                                        "id": tool_call.id,
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments,
                                    },
                                }
                            )

                    if chunk.usage:
                        yield ApiStreamUsageChunk(
                            input_tokens=chunk.usage.prompt_tokens or 0,
                            output_tokens=chunk.usage.completion_tokens or 0,
                            cache_write_tokens=getattr(
                                chunk.usage, "prompt_tokens_details", {}
                            ).get("cached_tokens", 0),
                            cache_read_tokens=getattr(chunk.usage, "prompt_tokens_details", {}).get(
                                "cached_tokens", 0
                            ),
                        )

        except Exception as e:
            raise RuntimeError(f"OpenAI API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self._model,
            max_tokens=4096,
            context_window=128000,
            supports_images=True,
            supports_prompt_cache=False,
            input_price=2.5,
            output_price=10.0,
            temperature=0.7,
        )
        return self._model, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        # This would be populated during streaming
        return None

    def abort(self) -> None:
        """Abort current request."""
        if self._current_stream:
            self._current_stream.close()

    def close(self) -> None:
        self._client = None


class AnthropicWrapper(LLMWrapper, ApiHandler):
    """Anthropic Claude API wrapper with streaming support and Cline compatibility."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None
        self._current_stream = None

    def _get_api_key_from_env(self) -> str:
        return os.getenv("HORDEFORGE_ANTHROPIC_API_KEY", "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                self._client = anthropic.Anthropic(
                    api_key=self._api_key,
                    timeout=self._timeout,
                    max_retries=0,  # We handle retries ourselves
                )
            except ImportError:
                pass
        return self._client

    def complete(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Anthropic client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = self._apply_retry(
                client.messages.create,
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
            )
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}") from e

        if not response.content:
            raise RuntimeError("Empty response from Anthropic API")

        return response.content[0].text

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Streaming completion using Anthropic Messages API."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("Anthropic client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            stream = client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
            )
        except Exception as e:
            raise RuntimeError(f"Anthropic API stream failed: {e}") from e

        with stream as event_stream:
            for event in event_stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield event.delta.text

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message with Cline-compatible interface."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("Anthropic client not available. Check API key.")

        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            anthropic_messages.append({"role": role, "content": content})

        try:
            stream = client.messages.stream(
                model=self._model,
                max_tokens=4000,
                system=system_prompt,
                messages=anthropic_messages,
                temperature=0.7,
                tools=tools,
            )

            with stream as event_stream:
                for event in event_stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield ApiStreamTextChunk(text=event.delta.text)

                    elif event.type == "content_block_start":
                        if (
                            hasattr(event.content_block, "type")
                            and event.content_block.type == "tool_use"
                        ):
                            yield ApiStreamToolCallsChunk(
                                tool_call={
                                    "call_id": event.content_block.id,
                                    "function": {
                                        "id": event.content_block.id,
                                        "name": event.content_block.name,
                                        "arguments": json.dumps(event.content_block.input),
                                    },
                                }
                            )

                    elif event.type == "message_delta":
                        if hasattr(event.delta, "usage"):
                            yield ApiStreamUsageChunk(
                                input_tokens=event.delta.usage.input_tokens or 0,
                                output_tokens=event.delta.usage.output_tokens or 0,
                                cache_write_tokens=getattr(
                                    event.delta.usage, "cache_creation_input_tokens", 0
                                ),
                                cache_read_tokens=getattr(
                                    event.delta.usage, "cache_read_input_tokens", 0
                                ),
                            )

        except Exception as e:
            raise RuntimeError(f"Anthropic API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self._model,
            max_tokens=6400,
            context_window=2000,
            supports_images=True,
            supports_prompt_cache=True,
            supports_reasoning=True,
            input_price=3.0,
            output_price=15.0,
            cache_writes_price=3.75,
            cache_reads_price=0.3,
            temperature=1.0,
        )
        return self._model, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        if self._current_stream:
            self._current_stream.cancel()

    def close(self) -> None:
        self._client = None


class GoogleGenAIWrapper(LLMWrapper, ApiHandler):
    """Google Gemini API wrapper with streaming support and Cline compatibility."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None
        self._current_stream = None

    def _get_api_key_from_env(self) -> str:
        return os.getenv("HORDEFORGE_GOOGLE_API_KEY", "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                genai.configure(api_key=self._api_key)
                self._client = genai.GenerativeModel(self._model)
            except ImportError:
                pass
        return self._client

    def complete(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Google GenAI client not available. Check API key.")

        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = client.generate_content(
                prompt,
                generation_config={
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_output_tokens": max_tokens,
                },
            )
        except Exception as e:
            raise RuntimeError(f"Google GenAI API call failed: {e}") from e

        if not response.text:
            raise RuntimeError("Empty response from Google GenAI API")

        return response.text

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Streaming completion using Google GenAI."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("Google GenAI client not available. Check API key.")

        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = client.generate_content(
                prompt,
                generation_config={
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_output_tokens": max_tokens,
                },
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"Google GenAI API stream failed: {e}") from e

        for chunk in response:
            if chunk.text:
                yield chunk.text

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message with Cline-compatible interface."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("Google GenAI client not available. Check API key.")

        # Combine system prompt with first user message
        full_prompt = f"{system_prompt}\n\n"

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            full_prompt += f"{role.capitalize()}: {content}\n\n"

        try:
            response = client.generate_content(
                full_prompt,
                generation_config={"temperature": 0.7},
                stream=True,
            )

            for chunk in response:
                if chunk.text:
                    yield ApiStreamTextChunk(text=chunk.text)

                # Note: Gemini doesn't have native tool calling in basic streaming
                # Advanced tool calling would require different approach

        except Exception as e:
            raise RuntimeError(f"Google GenAI API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self._model,
            max_tokens=8192,
            context_window=1048576,
            supports_images=True,
            supports_prompt_cache=True,
            supports_reasoning=True,
            input_price=0.15,
            output_price=0.6,
            cache_writes_price=1.0,
            cache_reads_price=0.025,
            temperature=1.0,
            supports_global_endpoint=True,
        )
        return self._model, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        if self._current_stream:
            # Gemini doesn't have direct abort mechanism in basic API
            pass

    def close(self) -> None:
        self._client = None


class QwenCodeWrapper(LLMWrapper):
    """Qwen Code wrapper backed by OAuth credentials JSON from profile store."""

    _AUTH_FAILURE_COOLDOWN_SECONDS = 300
    _auth_failure_until_by_fingerprint: dict[str, float] = {}

    def __init__(
        self,
        oauth_credentials_json: str,
        model: str = "qwen3-coder-plus",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        credentials_secret_ref: str | None = None,
        oauth_storage_dir: str | os.PathLike[str] | None = None,
    ):
        super().__init__(
            api_key=oauth_credentials_json, model=model, timeout=timeout, max_retries=max_retries
        )
        from agents.qwen_oauth_token_manager import QwenOAuthTokenManager

        self._token_manager = QwenOAuthTokenManager(
            oauth_credentials_json=oauth_credentials_json,
            credentials_secret_ref=credentials_secret_ref,
            storage_dir=oauth_storage_dir,
        )

    def _get_api_key_from_env(self) -> str:
        return ""

    @staticmethod
    def _resolve_base_url(credentials: dict[str, Any]) -> str:
        base_url = credentials.get(
            "resource_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        if not isinstance(base_url, str) or not base_url:
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            base_url = f"https://{base_url}"
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
        return base_url

    def _auth_failure_fingerprint(self) -> str:
        credentials = self._token_manager.get_current_credentials()
        refresh_token = credentials.get("refresh_token")
        access_token = credentials.get("access_token")
        refresh_tail = str(refresh_token)[-8:] if refresh_token else ""
        access_tail = str(access_token)[-8:] if access_token else ""
        return f"{refresh_tail}:{access_tail}"

    @staticmethod
    def _is_auth_error_message(message: str) -> bool:
        lowered = message.lower()
        return (
            "invalid_api_key" in lowered
            or "authenticationerror" in lowered
            or "access token expired" in lowered
            or "status code: 401" in lowered
            or "error code: 401" in lowered
        )

    def _mark_auth_failure(self) -> None:
        self._auth_failure_until_by_fingerprint[self._auth_failure_fingerprint()] = (
            time.time() + self._AUTH_FAILURE_COOLDOWN_SECONDS
        )

    def _raise_if_auth_cooldown(self) -> None:
        until = self._auth_failure_until_by_fingerprint.get(self._auth_failure_fingerprint(), 0.0)
        now = time.time()
        if until > now:
            remaining = int(until - now)
            raise RuntimeError(
                "Qwen Code auth cooldown active "
                f"({remaining}s remaining). Update llm.qwen-code.api_key secret."
            )

    def _client(self) -> OpenAI:
        credentials: dict[str, Any]
        try:
            credentials = self._token_manager.get_valid_credentials()
        except RuntimeError as exc:
            # Refresh endpoint may be transiently unavailable. Keep current
            # access token when present to avoid hard-failing requests.
            credentials = self._token_manager.get_current_credentials()
            current_access_token = credentials.get("access_token")
            if not isinstance(current_access_token, str) or not current_access_token:
                raise
            logger.warning(
                "qwen_oauth_refresh_failed_using_existing_access_token error=%s",
                exc,
            )

        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Qwen OAuth access_token is missing")
        return OpenAI(
            api_key=access_token,
            base_url=self._resolve_base_url(credentials),
            timeout=self._timeout,
            max_retries=0,
        )

    def complete(self, prompt: str, **kwargs) -> str:
        self._raise_if_auth_cooldown()
        client = self._client()
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)
        temperature = kwargs.get("temperature", 0.7)
        try:
            response = self._apply_retry(
                client.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
        except Exception as exc:
            if self._is_auth_error_message(str(exc)):
                self._mark_auth_failure()
                raise RuntimeError(f"Qwen Code authentication failed: {exc}") from exc
            # Fall back to streaming mode for providers that intermittently
            # return invalid non-stream payloads via OpenAI-compatible endpoint.
            pass

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            chunks: list[str] = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    chunks.append(chunk.choices[0].delta.content)
            text = "".join(chunks).strip()
            if text:
                return text
        except Exception as e:
            if self._is_auth_error_message(str(e)):
                self._mark_auth_failure()
            raise RuntimeError(f"Qwen Code API call failed: {e}") from e

        raise RuntimeError("Empty response from Qwen Code API")

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        client = self._client()
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"Qwen Code API stream failed: {e}") from e

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def close(self) -> None:
        return None


class ProfileFallbackLLMWrapper(LLMWrapper):
    """LLM wrapper that tries multiple configured profiles in order."""

    def __init__(
        self,
        profile_candidates: list[dict[str, Any]],
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key="", model="", timeout=timeout, max_retries=max_retries)
        self._profile_candidates = profile_candidates

    def _get_api_key_from_env(self) -> str:
        return ""

    def _build_wrapper_for_profile(self, profile: dict[str, Any]) -> LLMWrapper:
        provider = str(profile.get("provider", "")).strip().lower()
        if not provider:
            raise RuntimeError("LLM profile has no provider")
        kwargs: dict[str, Any] = {
            "timeout": self._timeout,
            "max_retries": self._max_retries,
        }
        model = profile.get("model")
        api_key = profile.get("api_key")
        api_key_ref = profile.get("api_key_ref")
        base_url = profile.get("base_url")
        if isinstance(model, str) and model.strip():
            kwargs["model"] = model.strip()
        if isinstance(api_key, str) and api_key.strip():
            kwargs["api_key"] = api_key
        if isinstance(api_key_ref, str) and api_key_ref.strip():
            kwargs["api_key_ref"] = api_key_ref.strip()
        if isinstance(base_url, str) and base_url.strip():
            kwargs["base_url"] = base_url.strip()
        wrapper = get_llm_wrapper(provider=provider, **kwargs)
        if wrapper is None:
            raise RuntimeError(f"LLM wrapper unavailable for provider '{provider}'")
        return wrapper

    @staticmethod
    def _profile_name(profile: dict[str, Any]) -> str:
        name = profile.get("profile_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return str(profile.get("provider", "unknown"))

    def complete(self, prompt: str, **kwargs) -> str:
        errors: list[str] = []
        for profile in self._profile_candidates:
            wrapper: LLMWrapper | None = None
            profile_name = self._profile_name(profile)
            try:
                wrapper = self._build_wrapper_for_profile(profile)
                return wrapper.complete(prompt, **kwargs)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{profile_name}: {str(exc)[:220]}")
                logger.warning(
                    "llm_profile_fallback_failed profile=%s provider=%s error=%s",
                    profile_name,
                    profile.get("provider"),
                    str(exc)[:500],
                )
            finally:
                if wrapper is not None:
                    try:
                        wrapper.close()
                    except Exception:  # noqa: BLE001
                        pass
        raise RuntimeError(
            "All configured LLM profiles failed. "
            + (" | ".join(errors) if errors else "No profile candidates available.")
        )

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        errors: list[str] = []
        for profile in self._profile_candidates:
            wrapper: LLMWrapper | None = None
            profile_name = self._profile_name(profile)
            try:
                wrapper = self._build_wrapper_for_profile(profile)
                yield from wrapper.complete_stream(prompt, **kwargs)
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{profile_name}: {str(exc)[:220]}")
                logger.warning(
                    "llm_profile_fallback_stream_failed profile=%s provider=%s error=%s",
                    profile_name,
                    profile.get("provider"),
                    str(exc)[:500],
                )
            finally:
                if wrapper is not None:
                    try:
                        wrapper.close()
                    except Exception:  # noqa: BLE001
                        pass
        raise RuntimeError(
            "All configured LLM profiles failed in stream mode. "
            + (" | ".join(errors) if errors else "No profile candidates available.")
        )

    def close(self) -> None:
        return None


def _load_profile_defaults(profile_name: str | None = None) -> dict[str, Any] | None:
    """Load LLM profile and secret from local profile store."""
    try:
        from cli.repo_store import get_llm_profile, get_secret_value
    except Exception:
        return None

    profile = get_llm_profile(profile_name)
    if not profile:
        return None

    provider = str(profile.get("provider", "")).strip().lower()
    model = str(profile.get("model", "")).strip()
    base_url = profile.get("base_url")
    api_key = None
    api_key_ref = profile.get("api_key_ref")
    if isinstance(api_key_ref, str) and api_key_ref.strip():
        api_key = get_secret_value(api_key_ref.strip())

    if not provider:
        return None
    return {
        "provider": provider,
        "model": model or None,
        "api_key": api_key,
        "api_key_ref": api_key_ref.strip()
        if isinstance(api_key_ref, str) and api_key_ref.strip()
        else None,
        "base_url": base_url if isinstance(base_url, str) and base_url.strip() else None,
    }


def _load_profile_candidates(profile_name: str | None = None) -> list[dict[str, Any]]:
    """Load profile candidates in priority order: selected/default first, then others."""
    try:
        from cli.repo_store import get_llm_profile, get_secret_value, list_llm_profiles
    except Exception:
        return []

    listed = list_llm_profiles()
    if not isinstance(listed, list) or not listed:
        return []

    by_name: dict[str, dict[str, Any]] = {}
    default_name: str | None = None
    for item in listed:
        if not isinstance(item, dict):
            continue
        name = item.get("profile_name")
        if not isinstance(name, str) or not name.strip():
            continue
        n = name.strip()
        by_name[n] = item
        if bool(item.get("is_default")) and default_name is None:
            default_name = n

    if not by_name:
        return []

    preferred = (
        profile_name.strip() if isinstance(profile_name, str) and profile_name.strip() else None
    )
    first_name = preferred if preferred in by_name else default_name
    if first_name is None:
        first_name = sorted(by_name.keys())[0]

    order = [first_name] + [name for name in by_name.keys() if name != first_name]
    candidates: list[dict[str, Any]] = []
    for name in order:
        profile = get_llm_profile(name)
        if not isinstance(profile, dict):
            continue
        provider = str(profile.get("provider", "")).strip().lower()
        if not provider:
            continue
        model = profile.get("model")
        base_url = profile.get("base_url")
        api_key = None
        api_key_ref = profile.get("api_key_ref")
        if isinstance(api_key_ref, str) and api_key_ref.strip():
            api_key = get_secret_value(api_key_ref.strip())
        candidates.append(
            {
                "profile_name": name,
                "provider": provider,
                "model": model if isinstance(model, str) and model.strip() else None,
                "api_key": api_key if isinstance(api_key, str) and api_key.strip() else None,
                "api_key_ref": api_key_ref.strip()
                if isinstance(api_key_ref, str) and api_key_ref.strip()
                else None,
                "base_url": base_url if isinstance(base_url, str) and base_url.strip() else None,
            }
        )
    return candidates


def get_llm_wrapper(
    provider: str | None = None,
    **kwargs,
) -> LLMWrapper | None:
    """Factory to get LLM wrapper."""
    resolved_provider = provider.strip().lower() if isinstance(provider, str) else ""

    if not resolved_provider:
        profile_name = os.getenv("HORDEFORGE_LLM_PROFILE", "").strip() or None
        profile_candidates = _load_profile_candidates(profile_name)
        if len(profile_candidates) > 1:
            return ProfileFallbackLLMWrapper(
                profile_candidates=profile_candidates,
                timeout=int(kwargs.get("timeout", DEFAULT_TIMEOUT)),
                max_retries=int(kwargs.get("max_retries", DEFAULT_MAX_RETRIES)),
            )
        if len(profile_candidates) == 1:
            candidate = profile_candidates[0]
            resolved_provider = candidate["provider"]
            if candidate.get("model") and not kwargs.get("model"):
                kwargs["model"] = candidate["model"]
            if candidate.get("api_key") and not kwargs.get("api_key"):
                kwargs["api_key"] = candidate["api_key"]
            if candidate.get("api_key_ref") and not kwargs.get("api_key_ref"):
                kwargs["api_key_ref"] = candidate["api_key_ref"]
            if candidate.get("base_url") and not kwargs.get("base_url"):
                kwargs["base_url"] = candidate["base_url"]

        profile_defaults = _load_profile_defaults(profile_name)
        if not resolved_provider and profile_defaults:
            resolved_provider = profile_defaults["provider"]
            if profile_defaults.get("model") and not kwargs.get("model"):
                kwargs["model"] = profile_defaults["model"]
            if profile_defaults.get("api_key") and not kwargs.get("api_key"):
                kwargs["api_key"] = profile_defaults["api_key"]
            if profile_defaults.get("api_key_ref") and not kwargs.get("api_key_ref"):
                kwargs["api_key_ref"] = profile_defaults["api_key_ref"]
            if profile_defaults.get("base_url") and not kwargs.get("base_url"):
                kwargs["base_url"] = profile_defaults["base_url"]

    if not resolved_provider:
        return None

    if resolved_provider == "openai":
        return OpenAIWrapper(**kwargs)
    elif resolved_provider == "anthropic":
        return AnthropicWrapper(**kwargs)
    elif resolved_provider == "google":
        return GoogleGenAIWrapper(**kwargs)
    elif resolved_provider == "qwen":
        qwen_base_url = (
            kwargs.pop("base_url", None) or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        return OpenAIWrapper(
            base_url=qwen_base_url,
            env_var_name="QWEN_API_KEY",
            **kwargs,
        )
    elif resolved_provider == "qwen-code":
        oauth_json = kwargs.get("api_key")
        if not isinstance(oauth_json, str) or not oauth_json.strip():
            raise RuntimeError("Qwen Code profile is missing OAuth credentials in secret store.")
        qwen_model = kwargs.get("model", "qwen3-coder-plus")
        api_key_ref = kwargs.get("api_key_ref")
        return QwenCodeWrapper(
            oauth_credentials_json=oauth_json,
            model=qwen_model,
            credentials_secret_ref=api_key_ref if isinstance(api_key_ref, str) else None,
        )
    elif resolved_provider:
        raise ValueError(f"Unknown LLM provider: {resolved_provider}")
    return None


# Backward compatibility imports and utilities
try:
    from .llm_wrapper_backward_compatibility import (
        LegacyLLMWrapper,
        MigrationFlags,
        get_legacy_llm_wrapper,
        get_migration_flag,
    )
except ImportError:
    # If backward compatibility module doesn't exist, create basic fallbacks
    class LegacyLLMWrapper:
        def __init__(self, provider="openai", **kwargs):
            self._wrapper = get_llm_wrapper(provider, **kwargs)

        def complete(self, prompt: str, **kwargs) -> str:
            return self._wrapper.complete(prompt, **kwargs)

        def complete_stream(self, prompt: str, **kwargs):
            return self._wrapper.complete_stream(prompt, **kwargs)

        def close(self):
            if hasattr(self._wrapper, "close"):
                self._wrapper.close()

    def get_legacy_llm_wrapper(provider="openai", **kwargs):
        return LegacyLLMWrapper(provider, **kwargs)

    # Set up basic migration flags
    class MigrationFlags:
        def __init__(self):
            self.flags = {
                "use_new_wrapper": True,
                "strict_compatibility": True,
                "allow_deprecated": True,
                "log_compatibility_warnings": True,
            }

        def get_flag(self, flag_name: str) -> bool:
            return self.flags.get(flag_name, False)

    _migration_flags = MigrationFlags()

    def get_migration_flag(flag_name: str) -> bool:
        return _migration_flags.get_flag(flag_name)


# Ensure backward compatibility is initialized
def _ensure_backward_compatibility():
    """Ensure backward compatibility layer is properly initialized."""
    # Use getattr to safely check if function exists
    init_logging = globals().get("initialize_compatibility_logging")
    if init_logging is not None and callable(init_logging):
        try:
            init_logging()
        except Exception:
            pass  # Ignore initialization errors


# Initialize backward compatibility on module load
_ensure_backward_compatibility()


# Functions that may be needed for backward compatibility
def build_code_review_prompt(files: list[dict[str, Any]], spec: dict[str, Any] = None) -> str:
    """Build prompt for code review - for backward compatibility."""
    from .llm_wrapper_backward_compatibility import legacy_build_code_prompt

    return legacy_build_code_prompt(spec or {}, files, {})


def parse_review_output(output: str) -> dict[str, Any]:
    """Parse review output - for backward compatibility."""
    import json
    import re

    # Try to extract JSON from output
    json_match = re.search(r"\{[\s\S]*\}", output)
    if not json_match:
        raise ValueError("No JSON found in LLM output")

    json_str = json_match.group(0)

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM output: {e}") from e

    # Validate required fields for review output
    required_fields = [
        "overall_decision",
        "summary",
        "findings",
        "strengths",
        "recommendations",
        "confidence",
    ]
    for _field in required_fields:
        if _field not in result:
            raise ValueError(f"Missing required field: {_field}")

    return result


# =============================================================================
# MODEL ROUTER (HF-P5-003)
# =============================================================================

# Task types for model routing
TASK_SPEC = "spec"
TASK_CODE = "code"
TASK_ANALYSIS = "analysis"
TASK_REFACTOR = "refactor"
TASK_REVIEW = "review"

# Default model configurations per task
# Using cheaper/faster models for simple tasks, stronger for complex
MODEL_ROUTING = {
    TASK_SPEC: {
        "provider": "google",
        "model": "gemini-2.0-flash",
        "description": "Fast spec generation",
    },
    TASK_CODE: {
        "provider": "openai",
        "model": "gpt-4o",
        "description": "Strong code generation",
    },
    TASK_ANALYSIS: {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "description": "Deep analysis",
    },
    TASK_REFACTOR: {
        "provider": "google",
        "model": "gemini-2.0-flash",
        "description": "Fast refactoring",
    },
    TASK_REVIEW: {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "description": "Thorough review",
    },
}

# Fallback mappings if primary provider fails
MODEL_ROUTING_FALLBACKS = {
    TASK_SPEC: TASK_CODE,
    TASK_CODE: TASK_ANALYSIS,
    TASK_ANALYSIS: TASK_CODE,
    TASK_REFACTOR: TASK_CODE,
    TASK_REVIEW: TASK_ANALYSIS,
}


class LLMRouter:
    """Router that selects optimal LLM wrapper based on task type.

    Usage:
        router = LLMRouter()
        llm = router.for_task("spec")  # Returns fast model for specs
        llm = router.for_task("code")  # Returns strong model for code
    """

    def __init__(
        self,
        custom_routing: dict[str, dict[str, str]] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize router with optional custom routing configuration.

        Args:
            custom_routing: Override default task->model mappings
            timeout: API timeout in seconds
            max_retries: Max retry attempts
        """
        self._routing = custom_routing or MODEL_ROUTING.copy()
        self._fallbacks = MODEL_ROUTING_FALLBACKS.copy()
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache: dict[str, LLMWrapper] = {}

    def for_task(self, task: str) -> LLMWrapper:
        """Get LLM wrapper optimized for the given task.

        Args:
            task: Task type (spec/code/analysis/refactor/review)

        Returns:
            Configured LLMWrapper instance

        Raises:
            ValueError: If task is unknown
        """
        if task not in self._routing:
            raise ValueError(f"Unknown task: {task}. Available: {list(self._routing.keys())}")

        # Return cached wrapper if available
        if task in self._cache:
            return self._cache[task]

        config = self._routing[task]
        provider = config["provider"]
        model = config["model"]

        wrapper = get_llm_wrapper(
            provider=provider,
            model=model,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

        if wrapper is None:
            # Try fallback
            fallback_task = self._fallbacks.get(task)
            if fallback_task:
                logger.warning(
                    f"Primary provider {provider} for task {task} unavailable, "
                    f"trying fallback: {fallback_task}"
                )
                return self.for_task(fallback_task)
            raise RuntimeError(f"No LLM provider available for task: {task}")

        # Cache the wrapper
        self._cache[task] = wrapper
        logger.info(f"Routed task '{task}' to {provider}/{model}: {config['description']}")

        return wrapper

    def for_model(self, provider: str, model: str) -> LLMWrapper:
        """Get LLM wrapper for specific provider and model.

        Args:
            provider: Provider name (openai/anthropic/google)
            model: Model name

        Returns:
            Configured LLMWrapper instance
        """
        key = f"{provider}:{model}"
        if key in self._cache:
            return self._cache[key]

        wrapper = get_llm_wrapper(
            provider=provider,
            model=model,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

        if wrapper is None:
            raise RuntimeError(f"Failed to create wrapper for {provider}/{model}")

        self._cache[key] = wrapper
        return wrapper

    def set_custom_route(
        self,
        task: str,
        provider: str,
        model: str,
        description: str = "",
    ) -> None:
        """Set custom routing for a task.

        Args:
            task: Task type
            provider: Provider name
            model: Model name
            description: Optional description
        """
        self._routing[task] = {
            "provider": provider,
            "model": model,
            "description": description or f"Custom: {provider}/{model}",
        }
        # Clear cache for this task
        self._cache.pop(task, None)

    def get_routing_info(self) -> dict[str, dict[str, str]]:
        """Get current routing configuration."""
        return self._routing.copy()

    def close_all(self) -> None:
        """Close all cached wrappers."""
        for wrapper in self._cache.values():
            if hasattr(wrapper, "close"):
                wrapper.close()
        self._cache.clear()


# =============================================================================
# SPECIFICATION PROMPT ENGINEERING (HF-P5-001)
# =============================================================================

SPEC_TYPE_API = "api"
SPEC_TYPE_UI = "ui"
SPEC_TYPE_BACKEND = "backend"
SPEC_TYPE_DATA = "data"

SPEC_TYPES = [SPEC_TYPE_API, SPEC_TYPE_UI, SPEC_TYPE_BACKEND, SPEC_TYPE_DATA]

# JSON schema for spec output validation
SPEC_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["summary", "requirements", "technical_notes", "file_changes"],
    "properties": {
        "summary": {"type": "string", "description": "Brief feature description"},
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "description", "test_criteria"],
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "test_criteria": {
                        "type": "string",
                        "description": "How to verify this requirement",
                    },
                    "priority": {"type": "string", "enum": ["must", "should", "could"]},
                },
            },
        },
        "technical_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "file_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "change_type", "description"],
                "properties": {
                    "path": {"type": "string"},
                    "change_type": {"type": "string", "enum": ["create", "modify", "delete"]},
                    "description": {"type": "string"},
                },
            },
        },
    },
}


def _get_api_spec_template() -> str:
    """Template for API-type specifications."""
    return """## API Specification Template

For each endpoint, specify:
- HTTP method and path
- Request parameters (path, query, body)
- Response format and status codes
- Authentication requirements
- Error handling

Provide OpenAPI-style definitions."""


def _get_ui_spec_template() -> str:
    """Template for UI-type specifications."""
    return """## UI Specification Template

For each component, specify:
- Component hierarchy and relationships
- User interactions and flows
- State management approach
- Responsive behavior
- Accessibility requirements

Include wireframe descriptions where relevant."""


def _get_backend_spec_template() -> str:
    """Template for backend-type specifications."""
    return """## Backend Specification Template

For each service/module, specify:
- Public interfaces and contracts
- Data models and schemas
- Business logic overview
- External dependencies
- Performance considerations

Include database schema changes if applicable."""


def _get_data_spec_template() -> str:
    """Template for data-type specifications."""
    return """## Data Specification Template

For data transformations, specify:
- Input data format and sources
- Output data format and destinations
- Transformation logic
- Data quality requirements
- Schema evolution strategy

Include data flow diagrams where relevant."""


def _get_spec_type_template(spec_type: str) -> str:
    """Get template for specific spec type."""
    templates = {
        SPEC_TYPE_API: _get_api_spec_template(),
        SPEC_TYPE_UI: _get_ui_spec_template(),
        SPEC_TYPE_BACKEND: _get_backend_spec_template(),
        SPEC_TYPE_DATA: _get_data_spec_template(),
    }
    return templates.get(spec_type, _get_backend_spec_template())


def detect_spec_type(issue_title: str, issue_body: str) -> str:
    """Detect the type of specification needed based on issue content."""
    content = (issue_title + " " + issue_body).lower()

    # API indicators
    api_keywords = ["api", "endpoint", "rest", "http", "request", "response", "crud"]
    # UI indicators
    ui_keywords = ["ui", "interface", "frontend", "button", "modal", "page", "view", "component"]
    # Data indicators
    data_keywords = ["data", "transform", "etl", "migration", "schema", "export", "import"]

    api_score = sum(1 for kw in api_keywords if kw in content)
    ui_score = sum(1 for kw in ui_keywords if kw in content)
    data_score = sum(1 for kw in data_keywords if kw in content)

    scores = [(SPEC_TYPE_API, api_score), (SPEC_TYPE_UI, ui_score), (SPEC_TYPE_DATA, data_score)]
    scores.sort(key=lambda x: x[1], reverse=True)

    if scores[0][1] > 0:
        return scores[0][0]
    return SPEC_TYPE_BACKEND  # Default


def build_spec_prompt(
    summary: str,
    requirements: list[str],
    context: dict[str, Any],
    spec_type: str | None = None,
) -> str:
    """Build enhanced prompt for specification generation.

    Args:
        summary: Feature summary from issue
        requirements: List of requirements from DoD
        context: Additional context (repo info, existing code, etc.)
        spec_type: Optional spec type (api/ui/backend/data). Auto-detected if not provided.
    """
    # Auto-detect spec type if not provided
    if spec_type is None:
        spec_type = detect_spec_type(summary, "\n".join(requirements))

    type_template = _get_spec_type_template(spec_type)

    template = f"""You are a senior software architect. Generate a detailed technical specification.

## Task Type
This is a **{spec_type.upper()}** feature.

## Feature Summary
{summary}

## Requirements (Definition of Done)
{chr(10).join(f"- {r}" for r in requirements)}

## Repository Context
{chr(10).join(f"- {k}: {v}" for k, v in context.items())}

## Type-Specific Guidance
{type_template}

## Output Format - STRICT JSON
Generate a JSON object with EXACTLY these fields:

{{
    "summary": "Brief 1-2 sentence description of the feature",
    "requirements": [
        {{
            "id": "REQ-001",
            "description": "Specific, testable requirement",
            "test_criteria": "How to verify this requirement passes",
            "priority": "must|should|could"
        }}
    ],
    "technical_notes": [
        "Implementation consideration 1",
        "Implementation consideration 2"
    ],
    "file_changes": [
        {{
            "path": "relative/path/to/file.py",
            "change_type": "create|modify|delete",
            "description": "What this file change accomplishes"
        }}
    ]
}}

## Critical Requirements:
1. Each requirement MUST have test_criteria that describes HOW to verify it
2. Requirements must be specific enough to write tests against
3. File changes must have concrete paths relative to project root
4. Response must be valid JSON only - no markdown code blocks, no explanations

Respond with valid JSON only.
"""
    return template


def parse_spec_output(output: str, validate_schema: bool = True) -> dict[str, Any]:
    """Parse and validate LLM spec output.

    Args:
        output: Raw LLM output
        validate_schema: Whether to validate against SPEC_OUTPUT_SCHEMA

    Returns:
        Parsed spec dictionary

    Raises:
        ValueError: If output cannot be parsed or is invalid
    """
    # Try to extract JSON from output (handle markdown code blocks)
    json_match = re.search(r"\{[\s\S]*\}", output)
    if not json_match:
        raise ValueError("No JSON found in LLM output")

    json_str = json_match.group(0)

    try:
        spec = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM output: {e}") from e

    # Validate required fields
    required_fields = ["summary", "requirements", "technical_notes", "file_changes"]
    for _field in required_fields:
        if _field not in spec:
            raise ValueError(f"Missing required field: {_field}")

    # Validate requirements structure
    for i, req in enumerate(spec.get("requirements", [])):
        if not isinstance(req, dict):
            raise ValueError(f"Requirement {i} is not an object")
        if "description" not in req:
            raise ValueError(f"Requirement {i} missing 'description'")
        if "test_criteria" not in req:
            raise ValueError(f"Requirement {i} missing 'test_criteria'")

    # Validate file_changes structure
    for i, fc in enumerate(spec.get("file_changes", [])):
        if not isinstance(fc, dict):
            raise ValueError(f"File change {i} is not an object")
        if "path" not in fc:
            raise ValueError(f"File change {i} missing 'path'")
        if "change_type" not in fc:
            raise ValueError(f"File change {i} missing 'change_type'")

    # Validate schema if requested
    if validate_schema:
        try:
            import jsonschema

            jsonschema.validate(spec, SPEC_OUTPUT_SCHEMA)
        except ImportError:
            pass  # jsonschema not available, skip validation
        except Exception as e:
            raise ValueError(f"Schema validation failed: {e}") from e

    return spec


def generate_spec_with_retry(
    llm: LLMWrapper,
    summary: str,
    requirements: list[str],
    context: dict[str, Any],
    spec_type: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Generate specification with retry logic.

    Args:
        llm: LLM wrapper instance
        summary: Feature summary
        requirements: List of requirements
        context: Additional context
        spec_type: Optional spec type
        max_retries: Maximum number of retry attempts

    Returns:
        Parsed and validated spec

    Raises:
        ValueError: If all retries fail
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            prompt = build_spec_prompt(summary, requirements, context, spec_type)
            output = llm.complete(prompt)
            spec = parse_spec_output(output)
            logger.info(f"Spec generated successfully on attempt {attempt + 1}")
            return spec
        except ValueError as e:
            last_error = e
            logger.warning(f"Spec generation attempt {attempt + 1} failed: {e}")

            # Add refinement hint for retry
            if attempt < max_retries - 1:
                context = context.copy()
                context["_retry_hint"] = f"Previous attempt failed: {e}. Ensure valid JSON output."

    raise ValueError(f"Spec generation failed after {max_retries} attempts: {last_error}")


# =============================================================================
# CODE PROMPT ENGINEERING (HF-P5-002)
# =============================================================================

# Language-specific coding standards
LANGUAGE_STANDARDS = {
    "python": {
        "style": "PEP 8",
        "typing": "Use type hints for all function signatures",
        "docstrings": "Use Google-style docstrings",
        "imports": "Organize: stdlib, third-party, local",
    },
    "javascript": {
        "style": "ESM, ESLint Airbnb",
        "typing": "Use TypeScript where possible",
        "docstrings": "JSDoc for public APIs",
        "imports": "Use ES6 imports",
    },
    "typescript": {
        "style": "Strict TypeScript",
        "typing": "No any types, use unknown instead",
        "docstrings": "TSDoc for public APIs",
        "imports": "Use ES6 imports with type annotations",
    },
    "go": {
        "style": "Standard Go formatting (gofmt)",
        "typing": "Strong typing, avoid interface{}",
        "docstrings": "Go doc conventions",
        "imports": "Use goimports",
    },
}


def detect_language(repo_context: dict[str, Any]) -> str:
    """Detect primary language from repository context."""
    # Check for language indicators in repo context
    files = repo_context.get("existing_files", [])
    extensions = set()
    for f in files:
        if "." in f:
            ext = f.rsplit(".", 1)[1]
            extensions.add(ext)

    ext_to_lang = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "jsx": "javascript",
        "tsx": "typescript",
        "go": "go",
        "rb": "ruby",
        "java": "java",
    }

    for ext in extensions:
        if ext in ext_to_lang:
            return ext_to_lang[ext]

    return "python"  # Default


def build_code_prompt(
    spec: dict[str, Any],
    test_cases: list[dict[str, Any]],
    repo_context: dict[str, Any],
    language: str | None = None,
) -> str:
    """Build enhanced prompt for code generation.

    Args:
        spec: Parsed specification from build_spec_prompt
        test_cases: List of test case definitions
        repo_context: Repository context (existing files, patterns, etc.)
        language: Optional language override. Auto-detected if not provided.
    """
    # Auto-detect language if not provided
    if language is None:
        language = detect_language(repo_context)

    standards = LANGUAGE_STANDARDS.get(language, LANGUAGE_STANDARDS["python"])

    # Extract existing code for context
    existing_code = _extract_relevant_code(repo_context, spec)

    template = f"""You are a senior {language.title()} engineer. Generate code to satisfy the specification.

## Language Standards
- Style: {standards["style"]}
- Typing: {standards["typing"]}
- Docstrings: {standards["docstrings"]}
- Imports: {standards["imports"]}

## Specification
{json.dumps(spec, indent=2)}

## Test Cases to Pass
{json.dumps(test_cases, indent=2)}

## Repository Context
{json.dumps(repo_context, indent=2)}

## Relevant Existing Code (for context)
{existing_code}

## Output Format - STRICT JSON
Generate a JSON object with EXACTLY these fields:

{{
    "files": [
        {{
            "path": "relative/path/to/file.py",
            "change_type": "create|modify|delete",
            "content": "FULL file content - include all existing code plus new changes"
        }}
    ],
    "decisions": [
        {{
            "description": "Architectural decision made",
            "rationale": "Why this approach was chosen"
        }}
    ],
    "test_changes": [
        {{
            "path": "path/to/test.py",
            "change_type": "create|modify",
            "content": "Test file content"
        }}
    ]
}}

## Critical Requirements:
1. For 'modify' changes, include FULL file content (not just diffs)
2. All imports must be valid and not conflict with existing code
3. Code must follow the specified language standards
4. Tests must verify the specification requirements
5. Response must be valid JSON only - no markdown code blocks

Respond with valid JSON only.
"""
    return template


def _extract_relevant_code(repo_context: dict[str, Any], spec: dict[str, Any]) -> str:
    """Extract relevant existing code for context injection."""
    files = repo_context.get("existing_files", [])
    file_contents = repo_context.get("file_contents", {})

    # Get file changes from spec to know what's relevant
    needed_paths = set()
    for fc in spec.get("file_changes", []):
        path = fc.get("path", "")
        if "/" in path:
            # Get directory
            dir_path = path.rsplit("/", 1)[0]
            needed_paths.add(dir_path)

    # Include files in same directories
    relevant = []
    for f in files:
        for needed in needed_paths:
            if f.startswith(needed) or needed in f:
                content = file_contents.get(f, "")
                if content:
                    relevant.append(f"=== {f} ===\n{content[:2000]}")
                break

    if not relevant:
        return "No relevant existing code found."

    return "\n\n".join(relevant)


def parse_code_output(output: str) -> dict[str, Any]:
    """Parse and validate LLM code generation output.

    Args:
        output: Raw LLM output

    Returns:
        Parsed code generation result

    Raises:
        ValueError: If output cannot be parsed or is invalid
    """
    # Try to extract JSON from output
    json_match = re.search(r"\{[\s\S]*\}", output)
    if not json_match:
        raise ValueError("No JSON found in LLM output")

    json_str = json_match.group(0)

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM output: {e}") from e

    # Validate required fields
    if "files" not in result:
        raise ValueError("Missing required field: files")

    # Validate files structure
    for i, f in enumerate(result.get("files", [])):
        if not isinstance(f, dict):
            raise ValueError(f"File {i} is not an object")
        if "path" not in f:
            raise ValueError(f"File {i} missing 'path'")
        if "change_type" not in f:
            raise ValueError(f"File {i} missing 'change_type'")
        if "content" not in f:
            raise ValueError(f"File {i} missing 'content'")

    return result


def generate_code_with_retry(
    llm: LLMWrapper,
    spec: dict[str, Any],
    test_cases: list[dict[str, Any]],
    repo_context: dict[str, Any],
    language: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Generate code with retry logic.

    Args:
        llm: LLM wrapper instance
        spec: Parsed specification
        test_cases: Test case definitions
        repo_context: Repository context
        language: Optional language override
        max_retries: Maximum number of retry attempts

    Returns:
        Parsed code generation result

    Raises:
        ValueError: If all retries fail
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            prompt = build_code_prompt(spec, test_cases, repo_context, language)
            output = llm.complete(prompt)
            result = parse_code_output(output)
            logger.info(f"Code generated successfully on attempt {attempt + 1}")
            return result
        except ValueError as e:
            last_error = e
            logger.warning(f"Code generation attempt {attempt + 1} failed: {e}")

    raise ValueError(f"Code generation failed after {max_retries} attempts: {last_error}")
