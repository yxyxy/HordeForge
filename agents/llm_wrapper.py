from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import anthropic
import google.genai as genai
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agents.qwen_dashscope import (
    build_chat_messages as build_qwen_chat_messages,
)
from agents.qwen_dashscope import (
    build_dashscope_headers,
)
from agents.qwen_dashscope import (
    resolve_base_url as resolve_qwen_base_url,
)
from agents.qwen_dashscope import (
    to_dashscope_content_parts as to_qwen_dashscope_content_parts,
)
from logging_utils import redact_sensitive_data
from observability.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    get_circuit_breaker_registry,
)

logger = logging.getLogger(__name__)

# Default timeout for API calls (seconds)
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3
_LLM_SESSION_LOGGING_ENV = "HORDEFORGE_LLM_SESSION_LOGGING"


def _llm_session_logging_mode() -> str:
    mode = str(os.getenv(_LLM_SESSION_LOGGING_ENV, "all") or "all").strip().lower()
    if mode not in {"off", "errors", "all"}:
        return "all"
    return mode


def _coerce_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _coerce_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_coerce_jsonable(item) for item in value]
    return repr(value)


def _sanitize_for_session_log(value: Any) -> Any:
    return _coerce_jsonable(redact_sensitive_data(value))


def _resolve_llm_sessions_dir() -> Path:
    override_dir = str(os.getenv("HORDEFORGE_LLM_SESSION_DIR", "") or "").strip()
    if override_dir:
        target = Path(override_dir)
        target.mkdir(parents=True, exist_ok=True)
        return target

    storage_dir = Path(os.getenv("HORDEFORGE_STORAGE_DIR", ".hordeforge_data"))
    last_logs_dir = storage_dir / "last_logs"
    if last_logs_dir.exists():
        target = last_logs_dir / "llm_sessions"
        target.mkdir(parents=True, exist_ok=True)
        return target

    target = storage_dir / "logs" / "current" / "llm_sessions"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_llm_session_record(payload: dict[str, Any]) -> None:
    try:
        sessions_dir = _resolve_llm_sessions_dir()
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
        file_name = f"{timestamp}_{uuid4().hex}.json"
        target_path = sessions_dir / file_name
        temp_path = target_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(target_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_session_write_failed error=%s", str(exc)[:300])


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


class SessionLoggingLLMWrapper(LLMWrapper):
    """Decorator that logs each LLM request/response into a dedicated session file."""

    def __init__(self, delegate: LLMWrapper, provider_name: str | None = None):
        model = str(getattr(delegate, "_model", "") or "unknown")
        super().__init__(api_key="", model=model, timeout=DEFAULT_TIMEOUT, max_retries=1)
        self._delegate = delegate
        self._provider_name = provider_name or delegate.__class__.__name__

    def _get_api_key_from_env(self) -> str:
        return ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def _build_record(
        self,
        *,
        prompt: str,
        kwargs: dict[str, Any],
        started_at: datetime,
        latency_ms: int,
        status: str,
        response: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": started_at.isoformat(),
            "provider": self._provider_name,
            "model": str(getattr(self._delegate, "_model", "") or "unknown"),
            "status": status,
            "latency_ms": latency_ms,
            "prompt": _sanitize_for_session_log(prompt),
            "request_kwargs": _sanitize_for_session_log(kwargs),
            "response": _sanitize_for_session_log(response) if response is not None else None,
            "error": _sanitize_for_session_log(error) if error is not None else None,
        }

    def complete(self, prompt: str, **kwargs) -> str:
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        mode = _llm_session_logging_mode()
        try:
            response = self._delegate.complete(prompt, **kwargs)
            if mode == "all":
                _write_llm_session_record(
                    self._build_record(
                        prompt=prompt,
                        kwargs=kwargs,
                        started_at=started_at,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        status="success",
                        response=response,
                    )
                )
            return response
        except Exception as exc:  # noqa: BLE001
            if mode in {"all", "errors"}:
                _write_llm_session_record(
                    self._build_record(
                        prompt=prompt,
                        kwargs=kwargs,
                        started_at=started_at,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        status="error",
                        error=str(exc),
                    )
                )
            raise

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        mode = _llm_session_logging_mode()
        chunks: list[str] = []
        try:
            for chunk in self._delegate.complete_stream(prompt, **kwargs):
                chunks.append(chunk)
                yield chunk
            if mode == "all":
                _write_llm_session_record(
                    self._build_record(
                        prompt=prompt,
                        kwargs=kwargs,
                        started_at=started_at,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        status="success",
                        response="".join(chunks),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            if mode in {"all", "errors"}:
                _write_llm_session_record(
                    self._build_record(
                        prompt=prompt,
                        kwargs=kwargs,
                        started_at=started_at,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        status="error",
                        response="".join(chunks) if chunks else None,
                        error=str(exc),
                    )
                )
            raise

    def close(self) -> None:
        self._delegate.close()


class CircuitBreakerLLMWrapper(LLMWrapper):
    """Decorator that wraps LLM calls with circuit breaker protection."""

    def __init__(self, delegate: LLMWrapper, provider_name: str | None = None):
        model = str(getattr(delegate, "_model", "") or "unknown")
        super().__init__(api_key="", model=model, timeout=DEFAULT_TIMEOUT, max_retries=1)
        self._delegate = delegate
        self._provider_name = provider_name or delegate.__class__.__name__
        self._circuit_breaker = get_circuit_breaker_registry().get_or_create(
            name=f"llm.{provider_name or model}",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=60.0,
                half_open_max_calls=3,
                ignore_exceptions=(RuntimeError,),
            ),
        )

    def _get_api_key_from_env(self) -> str:
        return ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def complete(self, prompt: str, **kwargs) -> str:
        def _call() -> str:
            return self._delegate.complete(prompt, **kwargs)

        try:
            return self._circuit_breaker.call(_call)
        except CircuitBreakerOpenError as exc:
            raise RuntimeError(
                f"LLM provider '{self._provider_name}' temporarily unavailable "
                f"(circuit breaker open): {exc}"
            ) from exc

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        try:
            # Yield chunks directly without buffering to avoid memory issues
            yield from self._delegate.complete_stream(prompt, **kwargs)
        except CircuitBreakerOpenError as exc:
            raise RuntimeError(
                f"LLM provider '{self._provider_name}' temporarily unavailable "
                f"(circuit breaker open): {exc}"
            ) from exc

    def close(self) -> None:
        self._delegate.close()


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
            maxTokens=4096,
            contextWindow=128000,
            supportsImages=True,
            supportsPromptCache=False,
            inputPrice=2.5,
            outputPrice=10.0,
            temperature=0.7,
        )
        return self._model, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        # This would be populated during streaming
        return None

    def complete_with_tools(
        self,
        *,
        prompt: str,
        tools: list[dict[str, Any]],
        tool_choice: str = "required",
        **kwargs,
    ) -> dict[str, Any]:
        """Function calling completion: returns tool_call arguments dict.

        Use this when you want the model to invoke a tool and return the parsed
        arguments directly, avoiding text-completion JSON parsing.

        Returns:
            dict with keys: {"name": str, "arguments": dict}
        """
        client = self._get_client()
        if client is None:
            raise RuntimeError("OpenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 8000)
        temperature = kwargs.get("temperature", 0.0)

        response = self._apply_retry(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )

        if not response.choices:
            raise RuntimeError("Empty response from OpenAI API (complete_with_tools)")

        message = response.choices[0].message
        if not message.tool_calls:
            raise RuntimeError("No tool_calls returned from OpenAI API (complete_with_tools)")

        tool_call = message.tool_calls[0]

        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse tool_call arguments: {e}. Raw: {tool_call.function.arguments[:200]}"
            ) from e

        return {
            "name": tool_call.function.name,
            "arguments": arguments,
            "call_id": tool_call.id,
        }

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
            maxTokens=6400,
            contextWindow=200000,
            supportsImages=True,
            supportsPromptCache=True,
            supportsReasoning=True,
            inputPrice=3.0,
            outputPrice=15.0,
            cacheWritesPrice=3.75,
            cacheReadsPrice=0.3,
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
            maxTokens=8192,
            contextWindow=1048576,
            supportsImages=True,
            supportsPromptCache=True,
            supportsReasoning=True,
            inputPrice=0.15,
            outputPrice=0.6,
            cacheWritesPrice=1.0,
            cacheReadsPrice=0.025,
            temperature=1.0,
            supportsGlobalEndpoint=True,
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
        self._auth_failure_until_by_fingerprint: dict[str, float] = {}
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
        return resolve_qwen_base_url(credentials)

    @staticmethod
    def _dashscope_headers() -> dict[str, str]:
        return build_dashscope_headers()

    @staticmethod
    def _to_dashscope_content_parts(content: Any) -> list[dict[str, str]]:
        return to_qwen_dashscope_content_parts(content)

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
            default_headers=self._dashscope_headers(),
            timeout=self._timeout,
            max_retries=0,
        )

    @staticmethod
    def _extract_error_diagnostics(exc: Exception) -> dict[str, Any]:
        status_code = getattr(exc, "status_code", None)
        request_id = getattr(exc, "request_id", None)
        content_type = None
        raw_body: str = ""

        response = getattr(exc, "response", None)
        if response is not None:
            if status_code is None:
                status_code = getattr(response, "status_code", None)
            headers = getattr(response, "headers", {}) or {}
            if isinstance(headers, dict):
                if request_id is None:
                    request_id = headers.get("x-request-id") or headers.get("request-id")
                content_type = headers.get("content-type") or headers.get("Content-Type")

            body = getattr(response, "text", None)
            if callable(body):
                try:
                    body = body()
                except Exception as e:  # noqa: BLE001
                    logger.debug("response_body_attr_access_failed error=%s", e)
                    body = None
            if body is None:
                body = getattr(response, "body", None)
            if body is None:
                body = getattr(response, "content", None)
            if isinstance(body, bytes):
                raw_body = body.decode("utf-8", errors="replace")
            elif isinstance(body, str):
                raw_body = body
            elif body is not None:
                raw_body = str(body)

        if not raw_body:
            raw_body = str(exc)

        raw_body = raw_body.strip()
        error_code = None
        if raw_body:
            try:
                parsed = json.loads(raw_body)
                if request_id is None and isinstance(parsed, dict):
                    rid = parsed.get("request_id")
                    if isinstance(rid, str) and rid.strip():
                        request_id = rid.strip()
                if isinstance(parsed, dict):
                    error_obj = parsed.get("error")
                    if isinstance(error_obj, dict):
                        code = error_obj.get("code")
                        if isinstance(code, str) and code.strip():
                            error_code = code.strip()
            except Exception as e:  # noqa: BLE001
                logger.debug("error_response_body_parse_failed error=%s", e)
        raw_excerpt = raw_body[:500]
        return {
            "status_code": status_code,
            "request_id": request_id,
            "content_type": content_type,
            "error_code": error_code,
            "raw_len": len(raw_body),
            "raw_excerpt": raw_excerpt,
        }

    @staticmethod
    def _is_non_retryable_status(status_code: int | None) -> bool:
        return status_code in {400, 401, 403}

    @staticmethod
    def _is_retryable_status(status_code: int | None) -> bool:
        if status_code is None:
            return False
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        message = str(exc).lower()
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        if "timeout" in message or "timed out" in message:
            return True
        if "connection reset" in message or "connection aborted" in message:
            return True
        return False

    @staticmethod
    def _backoff_with_jitter(attempt: int) -> float:
        base = min(8.0, 2 ** max(0, attempt - 1))
        return min(30.0, base + random.uniform(0.0, base * 0.3))

    def _complete_once(
        self,
        *,
        client: OpenAI,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        system_prompt = ""
        openai_messages = build_qwen_chat_messages(
            user_prompt=prompt,
            system_prompt=system_prompt,
        )
        non_stream_error: Exception | None = None
        try:
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices and response.choices[0].message.content:
                text = str(response.choices[0].message.content).strip()
                if text:
                    return text
        except Exception as exc:  # noqa: BLE001
            logger.debug("qwen_non_stream_fallback error=%s", exc)
            non_stream_error = exc

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=openai_messages,
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
        except Exception as exc:  # noqa: BLE001
            raise exc

        if non_stream_error is not None:
            raise non_stream_error
        raise RuntimeError("Empty response body from Qwen Code API")

    def complete(self, prompt: str, **kwargs) -> str:
        self._raise_if_auth_cooldown()
        client = self._client()
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)
        temperature = kwargs.get("temperature", 0.7)
        attempts = max(1, int(kwargs.get("max_retries", self._max_retries)))
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._complete_once(
                    client=client,
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as exc:  # noqa: BLE001
                if self._is_auth_error_message(str(exc)):
                    diagnostics = self._extract_error_diagnostics(exc)
                    logger.warning(
                        "qwen_llm_auth_failed provider=qwen-code model=%s request_id=%s "
                        "status_code=%s error_code=%s content_type=%s raw_len=%s raw_excerpt=%s error=%s",
                        model,
                        diagnostics.get("request_id"),
                        diagnostics.get("status_code"),
                        diagnostics.get("error_code"),
                        diagnostics.get("content_type"),
                        diagnostics.get("raw_len"),
                        diagnostics.get("raw_excerpt"),
                        str(exc)[:300],
                    )
                    self._mark_auth_failure()
                    raise RuntimeError(f"Qwen Code authentication failed: {exc}") from exc

                diagnostics = self._extract_error_diagnostics(exc)
                status_code = diagnostics.get("status_code")
                is_empty = "empty response body" in str(exc).lower()
                retryable = bool(
                    is_empty
                    or self._is_retryable_status(
                        status_code if isinstance(status_code, int) else None
                    )
                    or self._is_retryable_exception(exc)
                )
                if self._is_non_retryable_status(
                    status_code if isinstance(status_code, int) else None
                ):
                    retryable = False

                logger.warning(
                    "qwen_llm_request_failed provider=qwen-code model=%s attempt=%s/%s retryable=%s "
                    "request_id=%s status_code=%s error_code=%s content_type=%s raw_len=%s raw_excerpt=%s error=%s",
                    model,
                    attempt,
                    attempts,
                    retryable,
                    diagnostics.get("request_id"),
                    diagnostics.get("status_code"),
                    diagnostics.get("error_code"),
                    diagnostics.get("content_type"),
                    diagnostics.get("raw_len"),
                    diagnostics.get("raw_excerpt"),
                    str(exc)[:300],
                )

                last_exc = exc
                if not retryable or attempt >= attempts:
                    break

                sleep_seconds = self._backoff_with_jitter(attempt)
                logger.info(
                    "qwen_llm_retry_scheduled provider=qwen-code model=%s attempt=%s sleep_seconds=%.2f",
                    model,
                    attempt,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)  # Blocking: sync LLM retry backoff

        raise RuntimeError(f"Qwen Code API call failed: {last_exc}") from last_exc

    def complete_with_tools(
        self,
        *,
        prompt: str,
        tools: list[dict[str, Any]],
        tool_choice: str = "required",
        **kwargs,
    ) -> dict[str, Any]:
        """Function calling completion: returns tool_call arguments dict.

        Use this when you want the model to invoke a tool and return the parsed
        arguments directly, avoiding text-completion JSON parsing.

        Returns:
            dict with keys: {"name": str, "arguments": dict}
        """
        self._raise_if_auth_cooldown()
        client = self._client()
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 8000)
        temperature = kwargs.get("temperature", 0.0)
        attempts = max(1, int(kwargs.get("max_retries", self._max_retries)))
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                openai_messages = build_qwen_chat_messages(user_prompt=prompt, system_prompt="")
                response = client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                )

                if not response.choices:
                    raise RuntimeError("Empty response from Qwen Code API (complete_with_tools)")

                message = response.choices[0].message
                if not message.tool_calls:
                    raise RuntimeError(
                        "No tool_calls returned from Qwen Code API (complete_with_tools)"
                    )

                tool_call = message.tool_calls[0]
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"Failed to parse tool_call arguments: {e}. Raw: {tool_call.function.arguments[:200]}"
                    ) from e

                return {
                    "name": tool_call.function.name,
                    "arguments": arguments,
                    "call_id": tool_call.id,
                }

            except Exception as exc:  # noqa: BLE001
                if self._is_auth_error_message(str(exc)):
                    diagnostics = self._extract_error_diagnostics(exc)
                    logger.warning(
                        "qwen_llm_auth_failed provider=qwen-code model=%s request_id=%s "
                        "status_code=%s error_code=%s content_type=%s raw_len=%s raw_excerpt=%s error=%s",
                        model,
                        diagnostics.get("request_id"),
                        diagnostics.get("status_code"),
                        diagnostics.get("error_code"),
                        diagnostics.get("content_type"),
                        diagnostics.get("raw_len"),
                        diagnostics.get("raw_excerpt"),
                        str(exc)[:300],
                    )
                    self._mark_auth_failure()
                    raise RuntimeError(f"Qwen Code authentication failed: {exc}") from exc

                diagnostics = self._extract_error_diagnostics(exc)
                status_code = diagnostics.get("status_code")
                is_empty = "empty response body" in str(exc).lower()
                retryable = bool(
                    is_empty
                    or self._is_retryable_status(
                        status_code if isinstance(status_code, int) else None
                    )
                    or self._is_retryable_exception(exc)
                )
                if self._is_non_retryable_status(
                    status_code if isinstance(status_code, int) else None
                ):
                    retryable = False

                logger.warning(
                    "qwen_llm_request_failed provider=qwen-code model=%s attempt=%s/%s retryable=%s "
                    "request_id=%s status_code=%s error_code=%s content_type=%s raw_len=%s raw_excerpt=%s error=%s",
                    model,
                    attempt,
                    attempts,
                    retryable,
                    diagnostics.get("request_id"),
                    diagnostics.get("status_code"),
                    diagnostics.get("error_code"),
                    diagnostics.get("content_type"),
                    diagnostics.get("raw_len"),
                    diagnostics.get("raw_excerpt"),
                    str(exc)[:300],
                )

                last_exc = exc
                if not retryable or attempt >= attempts:
                    break

                sleep_seconds = self._backoff_with_jitter(attempt)
                logger.info(
                    "qwen_llm_retry_scheduled provider=qwen-code model=%s attempt=%s sleep_seconds=%.2f",
                    model,
                    attempt,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)  # Blocking: sync LLM retry backoff

        raise RuntimeError(f"Qwen Code API call failed: {last_exc}") from last_exc

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        client = self._client()
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)
        openai_messages = build_qwen_chat_messages(user_prompt=prompt, system_prompt="")
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=openai_messages,
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


class MimoAutoWrapper(LLMWrapper):
    """Wrapper for MiMo Code CLI (subprocess-based)."""

    def __init__(
        self,
        model: str = "mimo-auto",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs,
    ):
        super().__init__(api_key="mimo-cli", model=model, timeout=timeout, max_retries=max_retries)
        self._mimo_cmd = self._find_mimo_command()

    @staticmethod
    def _find_mimo_command() -> str | None:
        import shutil

        mimo_path = shutil.which("mimo")
        if mimo_path:
            return mimo_path
        npm_path = os.path.expanduser("~/AppData/Roaming/npm/mimo.cmd")
        if os.path.exists(npm_path):
            return npm_path
        return None

    def _get_api_key_from_env(self) -> str:
        return ""

    def complete(self, prompt: str, **kwargs) -> str:
        if not self._mimo_cmd:
            raise RuntimeError("'mimo' command not found. Install MiMo Code first.")

        system_prompt = kwargs.get("system_prompt", "")
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"

        try:
            result = subprocess.run(
                [self._mimo_cmd, "run", full_prompt],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            raise RuntimeError(f"mimo run failed: {result.stderr}")
        except FileNotFoundError as err:
            raise RuntimeError("'mimo' command not found. Install MiMo Code first.") from err
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"mimo run timed out after {self._timeout}s") from err

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        yield self.complete(prompt, **kwargs)

    def close(self) -> None:
        pass


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
        # Only qwen-code provider needs api_key_ref for OAuth token management.
        # For all other providers, do NOT pass api_key_ref as it causes
        # unexpected keyword argument errors in wrapper constructors.
        if provider == "qwen-code" and isinstance(api_key_ref, str) and api_key_ref.strip():
            kwargs["api_key_ref"] = api_key_ref.strip()
        if isinstance(base_url, str) and base_url.strip():
            kwargs["base_url"] = base_url.strip()
        wrapper = get_llm_wrapper(provider=provider, **kwargs)
        if wrapper is None:
            raise RuntimeError(f"LLM wrapper unavailable for provider '{provider}'")
        if wrapper is not None:
            # Ensure qwen-code gets valid OAuth credentials.
            # When the fallback path is used, the wrapper may be
            # initialised with stale tokens. Try to refresh them.
            self._try_refresh_qwen_oauth(wrapper)
        return wrapper

    @staticmethod
    def _try_refresh_qwen_oauth(wrapper) -> None:
        """Attempt to refresh Qwen OAuth tokens if the wrapper supports it."""
        token_manager = getattr(wrapper, "_token_manager", None)
        if token_manager is not None:
            try:
                token_manager.get_valid_credentials()
            except Exception as exc:
                logger.warning(
                    "llm_profile_qwen_oauth_refresh_failed model=%s error=%s",
                    getattr(wrapper, "_model", "unknown"),
                    str(exc)[:500],
                )

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
                    except Exception as e:  # noqa: BLE001
                        logger.debug(
                            "llm_profile_close_failed profile=%s error=%s", profile_name, e
                        )
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
                    except Exception as e:  # noqa: BLE001
                        logger.debug(
                            "llm_profile_close_failed profile=%s error=%s", profile_name, e
                        )
        raise RuntimeError(
            "All configured LLM profiles failed in stream mode. "
            + (" | ".join(errors) if errors else "No profile candidates available.")
        )

    def close(self) -> None:
        return None


def _load_profile_defaults(profile_name: str | None = None) -> dict[str, Any] | None:
    """Load LLM profile and secret, trying gateway first, then local."""
    profile = _load_profile_from_gateway(profile_name)

    if profile is None:
        try:
            from cli.repo_store import get_llm_profile as _local_get

            profile = _local_get(profile_name)
        except Exception as e:  # noqa: BLE001
            logger.debug("local_profile_load_failed profile=%s error=%s", profile_name, e)
            profile = None

    if not isinstance(profile, dict):
        return None

    provider = str(profile.get("provider", "")).strip().lower()
    model = str(profile.get("model", "")).strip()
    base_url = profile.get("base_url")
    api_key = None
    api_key_ref = profile.get("api_key_ref")
    if isinstance(api_key_ref, str) and api_key_ref.strip():
        api_key = _load_secret_with_gateway_fallback(api_key_ref.strip())

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


def _load_secret_with_gateway_fallback(key: str) -> str | None:
    """Load secret, trying gateway API first, then local secrets.json."""
    # Try gateway API first (primary source of truth)
    try:
        import os

        import requests as _requests

        gateway_url = os.getenv("HORDEFORGE_GATEWAY_URL", "http://localhost:8000")
        api_key = os.getenv("HORDEFORGE_OPERATOR_API_KEY")
        if api_key and gateway_url:
            resp = _requests.get(
                f"{gateway_url}/secrets",
                params={"name": key},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                value = data.get("value")
                if isinstance(value, str) and value.strip():
                    # Sync to local secrets.json for offline use
                    try:
                        from cli.repo_store import set_secret_value

                        set_secret_value(key, value)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("secret_sync_to_local_failed key=%s error=%s", key, e)
                    return value
    except Exception as e:  # noqa: BLE001
        logger.debug("gateway_secret_fetch_failed key=%s error=%s", key, e)

    # Fall back to local secrets.json
    try:
        from cli.repo_store import get_secret_value

        return get_secret_value(key)
    except Exception as e:  # noqa: BLE001
        logger.debug("local_secret_fallback_failed key=%s error=%s", key, e)
        return None


def _load_profile_from_gateway(profile_name: str | None = None) -> dict[str, Any] | None:
    """Load a single profile from gateway API."""
    try:
        import os

        import requests as _requests

        gateway_url = os.getenv("HORDEFORGE_GATEWAY_URL", "http://localhost:8000")
        api_key = os.getenv("HORDEFORGE_OPERATOR_API_KEY")
        if not gateway_url:
            return None
        resp = _requests.get(
            f"{gateway_url}/llm/profiles",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        direct_profile = data.get("profile")
        if isinstance(direct_profile, dict):
            return direct_profile
        profiles = data.get("profiles")
        if isinstance(profiles, list):
            if profile_name:
                for item in profiles:
                    if isinstance(item, dict) and item.get("profile_name") == profile_name:
                        return item
            default_profile = None
            for item in profiles:
                if not isinstance(item, dict):
                    continue
                if bool(item.get("is_default")):
                    default_profile = item
                    break
            if default_profile is not None:
                return default_profile
            if profiles:
                return profiles[0]
    except Exception as e:  # noqa: BLE001
        logger.debug("gateway_profile_load_failed profile=%s error=%s", profile_name, e)
        return None
    return None


def _load_profiles_from_gateway() -> list[dict[str, Any]]:
    """Load all profiles from gateway API."""
    try:
        import os

        import requests as _requests

        gateway_url = os.getenv("HORDEFORGE_GATEWAY_URL", "http://localhost:8000")
        api_key = os.getenv("HORDEFORGE_OPERATOR_API_KEY")
        if not gateway_url:
            return []
        resp = _requests.get(
            f"{gateway_url}/llm/profiles",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
            timeout=5,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        profiles = data.get("profiles")
        if isinstance(profiles, list):
            return [item for item in profiles if isinstance(item, dict)]
    except Exception as e:  # noqa: BLE001
        logger.debug("gateway_profiles_load_failed error=%s", e)
        return []
    return []


def _load_profile_candidates(profile_name: str | None = None) -> list[dict[str, Any]]:
    """Load profile candidates in priority order: selected/default first, then others."""
    listed = _load_profiles_from_gateway()
    get_profile = _load_profile_from_gateway
    if not listed:
        try:
            from cli.repo_store import get_llm_profile, list_llm_profiles

            listed = list_llm_profiles()
            get_profile = get_llm_profile
        except Exception as e:  # noqa: BLE001
            logger.debug("local_profiles_load_failed error=%s", e)
            return []
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
        profile = get_profile(name)
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
            api_key = _load_secret_with_gateway_fallback(api_key_ref.strip())
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

    wrapper: LLMWrapper | None
    if resolved_provider == "openai":
        wrapper = OpenAIWrapper(**kwargs)
    elif resolved_provider == "anthropic":
        wrapper = AnthropicWrapper(**kwargs)
    elif resolved_provider == "google":
        wrapper = GoogleGenAIWrapper(**kwargs)
    elif resolved_provider == "qwen":
        qwen_base_url = (
            kwargs.pop("base_url", None) or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        wrapper = OpenAIWrapper(
            base_url=qwen_base_url,
            env_var_name="QWEN_API_KEY",
            **kwargs,
        )
    elif resolved_provider == "mimo":
        wrapper = MimoAutoWrapper(**kwargs)
    elif resolved_provider == "qwen-code":
        oauth_json = kwargs.get("api_key")
        if not isinstance(oauth_json, str) or not oauth_json.strip():
            raise RuntimeError("Qwen Code profile is missing OAuth credentials in secret store.")
        qwen_model = kwargs.get("model", "qwen3-coder-plus")
        api_key_ref = kwargs.get("api_key_ref")
        wrapper = QwenCodeWrapper(
            oauth_credentials_json=oauth_json,
            model=qwen_model,
            credentials_secret_ref=api_key_ref if isinstance(api_key_ref, str) else None,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {resolved_provider}")

    if wrapper is None:
        return None

    if isinstance(wrapper, CircuitBreakerLLMWrapper):
        return wrapper

    # Wrap with session logging
    if not isinstance(wrapper, SessionLoggingLLMWrapper):
        if _llm_session_logging_mode() != "off":
            wrapper = SessionLoggingLLMWrapper(wrapper, provider_name=resolved_provider)

    # Wrap with circuit breaker (outermost layer)
    wrapper = CircuitBreakerLLMWrapper(wrapper, provider_name=resolved_provider)

    return wrapper


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
        except Exception as e:  # noqa: BLE001
            logger.debug("backward_compatibility_init_failed error=%s", e)


# Initialize backward compatibility on module load
_ensure_backward_compatibility()


# Functions that may be needed for backward compatibility
def build_code_review_prompt(files: list[dict[str, Any]], spec: dict[str, Any] = None) -> str:
    """Build prompt for code review - for backward compatibility."""
    from .llm_wrapper_backward_compatibility import legacy_build_code_prompt

    return legacy_build_code_prompt(spec or {}, files, {})


def parse_review_output(output: Any) -> dict[str, Any]:
    """Parse and normalize review output with backward-compatible defaults."""
    import json
    import re

    if isinstance(output, dict):
        cleaned = json.dumps(output, ensure_ascii=False)
    elif isinstance(output, list):
        cleaned = json.dumps(output, ensure_ascii=False)
    else:
        cleaned = str(output or "").strip()

    if not cleaned:
        raise ValueError("Empty LLM output")

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    parse_errors: list[str] = []

    def _try_parse(candidate: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as error:
            parse_errors.append(str(error))
        return None

    result = _try_parse(cleaned)

    if result is None:
        start_positions = [idx for idx, char in enumerate(cleaned) if char == "{"]
        for start in start_positions:
            depth = 0
            for idx in range(start, len(cleaned)):
                char = cleaned[idx]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start : idx + 1]
                        result = _try_parse(candidate)
                        if result is not None:
                            break
            if result is not None:
                break

    if result is None:
        detail = parse_errors[-1] if parse_errors else "No JSON object found"
        raise ValueError(f"Invalid JSON in LLM output: {detail}")

    if "overall_decision" not in result:
        if "decision" in result:
            result["overall_decision"] = result["decision"]
        else:
            for alias in ("overallDecision", "final_decision", "finalDecision", "review_decision"):
                if alias in result:
                    result["overall_decision"] = result[alias]
                    break

    if "overall_decision" not in result:
        result["overall_decision"] = "request_changes"

    if "summary" not in result:
        result["summary"] = ""

    if "findings" not in result:
        result["findings"] = []

    if "strengths" not in result:
        result["strengths"] = []

    if "recommendations" not in result:
        result["recommendations"] = []

    if "confidence" not in result:
        result["confidence"] = 0.7

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

    for i, finding in enumerate(result.get("findings", [])):
        if not isinstance(finding, dict):
            raise ValueError(f"Finding {i} is not an object")
        if "type" not in finding:
            raise ValueError(f"Finding {i} missing 'type'")
        if "severity" not in finding:
            raise ValueError(f"Finding {i} missing 'severity'")
        if "description" not in finding:
            raise ValueError(f"Finding {i} missing 'description'")

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


def _get_code_prompt_template() -> str:
    base_dir = Path(__file__).resolve().parent
    template_path = base_dir / "prompts" / "code_generator" / "base_prompt.v1.md"
    if template_path.exists():
        try:
            return template_path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.debug("prompt_template_read_failed path=%s error=%s", template_path, e)
    return (
        "You are a senior __LANGUAGE_TITLE__ engineer. Generate a minimal repository patch "
        "that satisfies the specification.\n\n"
        "## Language Standards\n"
        "- Style: __STYLE__\n"
        "- Typing: __TYPING__\n"
        "- Docstrings: __DOCSTRINGS__\n"
        "- Imports: __IMPORTS__\n\n"
        "## Specification\n"
        "__SPEC_JSON__\n\n"
        "## Tests To Satisfy\n"
        "__TESTS_JSON__\n\n"
        "## Repository Context\n"
        "__REPO_CONTEXT_JSON__\n\n"
        "## Relevant Existing Code\n"
        "__EXISTING_CODE__\n\n"
        "## Output Rules\n"
        "- Return VALID JSON only.\n"
        "- Do not wrap the JSON in markdown fences.\n"
        "- Touch the smallest possible number of files.\n"
        "- Prefer modifying existing likely files over inventing brand new modules.\n"
        "- Preferred output is patch_text in Codex apply_patch format.\n"
        "- Prefer operations over raw full-file rewrites whenever possible.\n"
        "- If you use edit operations, NEVER escape old_string/new_string; send exact literal text.\n"
        "- Raw files[] fallback is allowed, but only when an exact edit/write operation would be worse.\n"
        "- For each touched file entry in files[], include the final full content for that touched file only.\n"
        "- Preserve untouched regions byte-for-byte where possible; do not rewrite entire files without need.\n"
        '- If a test file is included, put it in "test_changes" or "test_operations".\n'
        "- Do not output prose before or after the JSON object.\n\n"
        "## Required JSON Schema\n"
        "{\n"
        '  "patch_text": "*** Begin Patch\\n*** Update File: path/to/file.py\\n@@\\n-old\\n+new\\n*** End Patch",\n'
        '  "operations": [\n'
        '    {"type":"edit|write","path":"relative/path/to/file.py","old_string":"exact old text for edit","new_string":"exact new text for edit","replace_all":false,"content":"final content for write","change_type":"create|modify|delete"}\n'
        "  ],\n"
        '  "files": [{"path":"relative/path/to/file.py","change_type":"create|modify|delete","content":"final content of the touched file"}],\n'
        '  "decisions":[{"description":"Architectural decision made","rationale":"Why this approach was chosen"}],\n'
        '  "test_operations":[{"type":"edit|write","path":"tests/test_example.py","old_string":"exact old text","new_string":"exact new text","replace_all":false,"content":"final content for write","change_type":"create|modify|delete"}],\n'
        '  "test_changes":[{"path":"tests/test_example.py","change_type":"create|modify","content":"final content of the touched test file"}]\n'
        "}\n\n"
        "Respond with valid JSON only.\n"
    )


def build_code_prompt(
    spec: dict[str, Any],
    test_cases: list[dict[str, Any]],
    repo_context: dict[str, Any],
    language: str | None = None,
) -> str:
    """Build enhanced prompt for code generation."""

    if language is None:
        language = detect_language(repo_context)

    standards = LANGUAGE_STANDARDS.get(language, LANGUAGE_STANDARDS["python"])
    existing_code = _extract_relevant_code(repo_context, spec)

    compact_spec = {
        "summary": spec.get("summary"),
        "acceptance_criteria": (spec.get("acceptance_criteria") or [])[:8],
        "technical_notes": (spec.get("technical_notes") or [])[:8],
        "file_change_plan": spec.get("file_change_plan") or {},
        "requirements": (spec.get("requirements") or [])[:8],
    }
    compact_tests = []
    for case in test_cases[:10]:
        if not isinstance(case, dict):
            continue
        compact_tests.append(
            {
                "name": case.get("name"),
                "file_path": case.get("file_path"),
                "description": case.get("description"),
                "expected_result": case.get("expected_result"),
            }
        )
    compact_repo_context = _compact_repo_context_for_prompt(repo_context)

    template = _get_code_prompt_template()
    replacements = {
        "__LANGUAGE_TITLE__": language.title(),
        "__STYLE__": standards["style"],
        "__TYPING__": standards["typing"],
        "__DOCSTRINGS__": standards["docstrings"],
        "__IMPORTS__": standards["imports"],
        "__SPEC_JSON__": json.dumps(compact_spec, ensure_ascii=False, indent=2),
        "__TESTS_JSON__": json.dumps(compact_tests, ensure_ascii=False, indent=2),
        "__REPO_CONTEXT_JSON__": json.dumps(compact_repo_context, ensure_ascii=False, indent=2),
        "__EXISTING_CODE__": existing_code,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
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
    if not needed_paths:
        for path in repo_context.get("candidate_files", [])[:4]:
            normalized = str(path or "").strip()
            if "/" in normalized:
                needed_paths.add(normalized.rsplit("/", 1)[0])

    # Include files in same directories
    relevant = []
    for f in files:
        if not isinstance(f, str) or not f.strip():
            continue
        if needed_paths and not any(f.startswith(needed) or needed in f for needed in needed_paths):
            continue
        content = file_contents.get(f, "")
        if content:
            relevant.append(f"=== {f} ===\n{content}")
        if len(relevant) >= 6:
            break

    if not relevant:
        return "No relevant existing code found."

    return "\n\n".join(relevant)


def _compact_repo_context_for_prompt(repo_context: dict[str, Any]) -> dict[str, Any]:
    compact = dict(repo_context)
    file_contents = compact.pop("file_contents", {})
    if isinstance(file_contents, dict) and file_contents:
        compact["loaded_file_context"] = [
            {
                "path": str(path),
                "chars": len(str(content)),
            }
            for path, content in list(file_contents.items())[:4]
            if str(path).strip()
        ]
    snippets = compact.get("candidate_file_snippets")
    if isinstance(snippets, list):
        compact["candidate_file_snippets"] = [
            {
                "path": item.get("path"),
                "snippet": item.get("snippet"),
                "truncated": item.get("truncated", False),
                "has_full_content": bool(item.get("content")),
            }
            for item in snippets[:4]
            if isinstance(item, dict)
        ]
    return compact


def parse_code_output(output: str) -> dict[str, Any]:
    """Parse and validate LLM code generation output."""

    if not isinstance(output, str) or not output.strip():
        raise ValueError("Empty LLM output")

    cleaned = output.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    decoder = json.JSONDecoder()
    last_error: Exception | None = None
    parsed_result: dict[str, Any] | None = None

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(candidate, dict) and (
            "files" in candidate
            or "operations" in candidate
            or "patch_text" in candidate
            or "required_files" in candidate
        ):
            parsed_result = candidate
            break

    if parsed_result is None:
        raise ValueError(
            "No valid JSON object with 'files', 'operations', or 'patch_text' found "
            f"in LLM output: {last_error}"
        )

    result = parsed_result

    result.setdefault("files", [])
    result.setdefault("operations", [])
    result.setdefault("patch_text", "")
    result.setdefault("decisions", [])
    result.setdefault("test_operations", [])
    result.setdefault("test_changes", [])
    if not isinstance(result.get("files"), list):
        raise ValueError("Field 'files' must be a list")
    if not isinstance(result.get("operations"), list):
        raise ValueError("Field 'operations' must be a list")
    if not isinstance(result.get("patch_text"), str):
        raise ValueError("Field 'patch_text' must be a string")
    if not isinstance(result.get("decisions"), list):
        raise ValueError("Field 'decisions' must be a list")
    if not isinstance(result.get("test_operations"), list):
        raise ValueError("Field 'test_operations' must be a list")
    if not isinstance(result.get("test_changes"), list):
        raise ValueError("Field 'test_changes' must be a list")

    if not result["files"] and not result["operations"] and not result["patch_text"].strip():
        required_files = result.get("required_files")
        if not isinstance(required_files, list) or not required_files:
            raise ValueError(
                "At least one of 'files', 'operations', or 'patch_text' must be non-empty"
            )

    for i, f in enumerate(result.get("files", [])):
        if not isinstance(f, dict):
            raise ValueError(f"File {i} is not an object")
        if "path" not in f or not isinstance(f.get("path"), str) or not f.get("path", "").strip():
            raise ValueError(f"File {i} missing valid 'path'")
        if "change_type" not in f or not isinstance(f.get("change_type"), str):
            raise ValueError(f"File {i} missing 'change_type'")
        if "content" not in f or not isinstance(f.get("content"), str):
            raise ValueError(f"File {i} missing 'content'")

    for i, operation in enumerate(result.get("operations", [])):
        if not isinstance(operation, dict):
            raise ValueError(f"Operation {i} is not an object")
        operation_type = operation.get("type")
        if not isinstance(operation_type, str) or operation_type not in {"edit", "write"}:
            raise ValueError(f"Operation {i} missing valid 'type'")
        if "path" not in operation or not isinstance(operation.get("path"), str):
            raise ValueError(f"Operation {i} missing valid 'path'")
        if operation_type == "edit":
            if "old_string" not in operation or not isinstance(operation.get("old_string"), str):
                raise ValueError(f"Operation {i} missing 'old_string'")
            if "new_string" not in operation or not isinstance(operation.get("new_string"), str):
                raise ValueError(f"Operation {i} missing 'new_string'")
        if operation_type == "write":
            if "content" not in operation or not isinstance(operation.get("content"), str):
                raise ValueError(f"Operation {i} missing 'content'")

    for i, f in enumerate(result.get("test_changes", [])):
        if not isinstance(f, dict):
            raise ValueError(f"Test change {i} is not an object")
        if "path" not in f or not isinstance(f.get("path"), str) or not f.get("path", "").strip():
            raise ValueError(f"Test change {i} missing valid 'path'")
        if "change_type" not in f or not isinstance(f.get("change_type"), str):
            raise ValueError(f"Test change {i} missing 'change_type'")
        if "content" not in f or not isinstance(f.get("content"), str):
            raise ValueError(f"Test change {i} missing 'content'")

    for i, operation in enumerate(result.get("test_operations", [])):
        if not isinstance(operation, dict):
            raise ValueError(f"Test operation {i} is not an object")
        operation_type = operation.get("type")
        if not isinstance(operation_type, str) or operation_type not in {"edit", "write"}:
            raise ValueError(f"Test operation {i} missing valid 'type'")
        if "path" not in operation or not isinstance(operation.get("path"), str):
            raise ValueError(f"Test operation {i} missing valid 'path'")

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
