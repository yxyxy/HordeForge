from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from openai import OpenAI

from .llm_wrapper import (
    ApiHandler,
    ApiStream,
    ApiStreamTextChunk,
    ApiStreamThinkingChunk,
    ApiStreamToolCallsChunk,
    ApiStreamUsageChunk,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class OllamaHandler(ApiHandler):
    """Ollama API handler with streaming support."""

    def __init__(
        self,
        ollama_base_url: str | None = None,
        ollama_api_key: str | None = None,
        ollama_model_id: str = "llama2",
        ollama_ctx_num: int = 32768,
        request_timeout_ms: int = 30000,
    ):
        self.ollama_base_url = ollama_base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.ollama_api_key = ollama_api_key
        self.ollama_model_id = ollama_model_id
        self.ollama_ctx_num = ollama_ctx_num
        self.request_timeout_ms = request_timeout_ms

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Ollama API."""
        import aiohttp

        # Convert messages to Ollama format
        ollama_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ollama_messages.append({"role": role, "content": content})

        payload = {
            "model": self.ollama_model_id,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "num_ctx": self.ollama_ctx_num,
            },
        }

        if tools:
            payload["tools"] = tools

        headers = {}
        if self.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.ollama_api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_base_url}/api/chat",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout_ms / 1000),
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Ollama API error: {response.status}")

                    async for line in response.content:
                        if line.strip():
                            try:
                                chunk_data = json.loads(line.decode())

                                if chunk_data.get("done"):
                                    break

                                if "message" in chunk_data:
                                    message = chunk_data["message"]
                                    if message.get("role") == "assistant" and message.get(
                                        "content"
                                    ):
                                        yield ApiStreamTextChunk(text=message["content"])

                                    # Handle tool calls
                                    if message.get("tool_calls"):
                                        for tool_call in message["tool_calls"]:
                                            yield ApiStreamToolCallsChunk(
                                                tool_call={
                                                    "call_id": tool_call.get("id"),
                                                    "function": {
                                                        "id": tool_call.get("id"),
                                                        "name": tool_call.get("function", {}).get(
                                                            "name"
                                                        ),
                                                        "arguments": tool_call.get(
                                                            "function", {}
                                                        ).get("arguments"),
                                                    },
                                                }
                                            )

                                    # Handle usage with enhanced token tracking
                                    if (
                                        "eval_count" in chunk_data
                                        or "prompt_eval_count" in chunk_data
                                    ):
                                        yield ApiStreamUsageChunk(
                                            input_tokens=chunk_data.get("prompt_eval_count", 0),
                                            output_tokens=chunk_data.get("eval_count", 0),
                                            cache_write_tokens=chunk_data.get(
                                                "cache_creation_input_tokens", 0
                                            ),
                                            cache_read_tokens=chunk_data.get(
                                                "cache_read_input_tokens", 0
                                            ),
                                        )
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            raise RuntimeError(f"Ollama API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.ollama_model_id,
            maxTokens=4096,
            contextWindow=self.ollama_ctx_num,
            supportsImages=False,
            supportsPromptCache=False,
            inputPrice=0.0,
            outputPrice=0.0,
            temperature=0.7,
        )
        return self.ollama_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""


class ClaudeCodeHandler(ApiHandler):
    """Claude Code API handler with streaming support."""

    def __init__(
        self,
        claude_code_path: str | None = None,
        claude_code_model_id: str = "claude-sonnet-4-20250514",
        thinking_budget_tokens: int = 0,
    ):
        self.claude_code_path = claude_code_path or os.getenv("CLAUDE_CODE_PATH")
        self.claude_code_model_id = claude_code_model_id
        self.thinking_budget_tokens = thinking_budget_tokens

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Claude Code CLI."""
        import json
        import subprocess

        # Filter out image blocks since Claude Code doesn't support them
        filtered_messages = self._filter_messages_for_claude_code(messages)

        # Prepare Claude Code CLI command
        cmd = [
            "claude-code",  # This assumes claude-code CLI is installed and in PATH
            "--model",
            self.claude_code_model_id,
            "--system",
            system_prompt,
        ]

        if self.thinking_budget_tokens > 0:
            cmd.extend(["--thinking-budget", str(self.thinking_budget_tokens)])

        if self.claude_code_path:
            cmd.extend(["--path", self.claude_code_path])

        try:
            # Start the Claude Code process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Send messages as JSON input
            input_data = json.dumps(filtered_messages)
            stdout, stderr = await process.communicate(input=input_data)

            if process.returncode != 0:
                raise RuntimeError(f"Claude Code CLI error: {stderr}")

            # Parse and yield the response
            lines = stdout.strip().split("\n")
            for line in lines:
                if line.strip():
                    try:
                        chunk = json.loads(line)

                        # Handle different chunk types
                        if isinstance(chunk, str):
                            yield ApiStreamTextChunk(text=chunk)
                        elif isinstance(chunk, dict):
                            if chunk.get("type") == "assistant":
                                # Handle assistant message content
                                content_blocks = chunk.get("message", {}).get("content", [])
                                for content in content_blocks:
                                    if content.get("type") == "text":
                                        yield ApiStreamTextChunk(text=content.get("text", ""))
                                    elif content.get("type") == "thinking":
                                        yield ApiStreamThinkingChunk(
                                            reasoning=content.get("thinking", "")
                                        )
                                    elif content.get("type") == "tool_use":
                                        yield ApiStreamToolCallsChunk(
                                            tool_call={
                                                "call_id": content.get("id"),
                                                "function": {
                                                    "id": content.get("id"),
                                                    "name": content.get("name"),
                                                    "arguments": json.dumps(
                                                        content.get("input", {})
                                                    ),
                                                },
                                            }
                                        )
                            elif chunk.get("type") == "usage":
                                # Handle usage information
                                yield ApiStreamUsageChunk(
                                    input_tokens=chunk.get("input_tokens", 0),
                                    output_tokens=chunk.get("output_tokens", 0),
                                    cache_read_tokens=chunk.get("cache_read_tokens", 0),
                                    cache_write_tokens=chunk.get("cache_write_tokens", 0),
                                )
                    except json.JSONDecodeError:
                        # If it's not JSON, treat as plain text
                        yield ApiStreamTextChunk(text=line)

        except Exception as e:
            raise RuntimeError(f"Claude Code API stream failed: {e}") from e

    def _filter_messages_for_claude_code(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Filter out image blocks since Claude Code doesn't support them."""
        filtered = []
        for msg in messages:
            # Remove any image-related content or filter as needed
            # For now, we'll pass through the messages as-is
            # In a real implementation, this would filter out image content
            filtered.append(msg)
        return filtered

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.claude_code_model_id,
            maxTokens=6400,
            contextWindow=2000,
            supportsImages=False,
            supportsPromptCache=True,
            supportsReasoning=True,
            inputPrice=3.0,
            outputPrice=15.0,
            cacheWritesPrice=3.75,
            cacheReadsPrice=0.3,
            temperature=1.0,
        )
        return self.claude_code_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass

    pass


class GeminiHandler(ApiHandler):
    """Google Gemini API handler with streaming support."""

    def __init__(
        self,
        gemini_api_key: str | None = None,
        gemini_model_id: str = "gemini-pro",
        gemini_base_url: str | None = None,
        thinking_budget_tokens: int = 0,
        reasoning_effort: str = "low",
    ):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model_id = gemini_model_id
        self.gemini_base_url = gemini_base_url
        self.thinking_budget_tokens = thinking_budget_tokens
        self.reasoning_effort = reasoning_effort

        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Gemini API."""
        import google.generativeai as genai

        genai.configure(api_key=self.gemini_api_key)
        model = genai.GenerativeModel(self.gemini_model_id)

        # Combine system prompt with messages
        full_prompt = f"{system_prompt}\n\n"
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            full_prompt += f"{role.capitalize()}: {content}\n\n"

        try:
            response = model.generate_content(
                full_prompt,
                stream=True,
                tools=tools,
            )

            for chunk in response:
                if chunk.text:
                    yield ApiStreamTextChunk(text=chunk.text)

                # Handle usage metadata
                if hasattr(chunk, "usage_metadata"):
                    usage = chunk.usage_metadata
                    yield ApiStreamUsageChunk(
                        input_tokens=usage.prompt_token_count or 0,
                        output_tokens=usage.candidates_token_count or 0,
                        cache_read_tokens=usage.cached_content_token_count or 0,
                    )

        except Exception as e:
            raise RuntimeError(f"Gemini API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.gemini_model_id,
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
        return self.gemini_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class OpenRouterHandler(ApiHandler):
    """OpenRouter API handler with streaming support."""

    def __init__(
        self,
        openrouter_api_key: str | None = None,
        openrouter_model_id: str = "openai/gpt-4o",
        reasoning_effort: str = "low",
        thinking_budget_tokens: int = 0,
        enable_parallel_tool_calling: bool = False,
    ):
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model_id = openrouter_model_id
        self.reasoning_effort = reasoning_effort
        self.thinking_budget_tokens = thinking_budget_tokens
        self.enable_parallel_tool_calling = enable_parallel_tool_calling

        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using OpenRouter API."""
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.openrouter_api_key,
            default_headers={
                "HTTP-Referer": "https://cline.bot",
                "X-Title": "Cline",
            },
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.openrouter_model_id,
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
                            total_cost=chunk.usage.cost if hasattr(chunk.usage, "cost") else None,
                        )

        except Exception as e:
            raise RuntimeError(f"OpenRouter API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.openrouter_model_id,
            max_tokens=4096,
            context_window=128000,
            supports_images=True,
            supports_prompt_cache=False,
            input_price=2.5,
            output_price=10.0,
            temperature=0.7,
        )
        return self.openrouter_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class AwsBedrockHandler(ApiHandler):
    """AWS Bedrock API handler with streaming support."""

    def __init__(
        self,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_region: str = "us-east-1",
        aws_session_token: str | None = None,
        aws_bedrock_api_key: str | None = None,
        aws_bedrock_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        thinking_budget_tokens: int = 0,
    ):
        self.aws_access_key = aws_access_key or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = aws_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = aws_region
        self.aws_session_token = aws_session_token
        self.aws_bedrock_api_key = aws_bedrock_api_key
        self.aws_bedrock_model_id = aws_bedrock_model_id
        self.thinking_budget_tokens = thinking_budget_tokens

        if not (self.aws_access_key and self.aws_secret_key):
            raise ValueError("AWS credentials must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using AWS Bedrock API."""
        import boto3

        client = boto3.client(
            "bedrock-runtime",
            region_name=self.aws_region,
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            aws_session_token=self.aws_session_token,
        )

        # Convert messages to Bedrock format
        bedrock_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            bedrock_messages.append({"role": role, "content": [{"text": content}]})

        try:
            response = client.converse_stream(
                modelId=self.aws_bedrock_model_id,
                messages=bedrock_messages,
                system=[{"text": system_prompt}],
                inferenceConfig={
                    "temperature": 0.7,
                    "maxTokens": 4000,
                },
                toolConfig={"tools": tools or []} if tools else {},
            )

            for chunk in response["stream"]:
                if "contentBlockDelta" in chunk:
                    delta = chunk["contentBlockDelta"]
                    if delta.get("delta", {}).get("text"):
                        yield ApiStreamTextChunk(text=delta["delta"]["text"])

                elif "usage" in chunk:
                    usage = chunk["usage"]
                    yield ApiStreamUsageChunk(
                        input_tokens=usage.get("inputTokens", 0),
                        output_tokens=usage.get("outputTokens", 0),
                    )

        except Exception as e:
            raise RuntimeError(f"AWS Bedrock API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.aws_bedrock_model_id,
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
            supports_global_endpoint=True,
        )
        return self.aws_bedrock_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class VertexHandler(ApiHandler):
    """Google Vertex AI handler with streaming support."""

    def __init__(
        self,
        vertex_project_id: str | None = None,
        vertex_region: str = "us-central1",
        vertex_api_key: str | None = None,
        vertex_model_id: str = "gemini-1.5-pro-001",
        thinking_budget_tokens: int = 0,
    ):
        self.vertex_project_id = vertex_project_id or os.getenv("VERTEX_PROJECT_ID")
        self.vertex_region = vertex_region
        self.vertex_api_key = vertex_api_key
        self.vertex_model_id = vertex_model_id
        self.thinking_budget_tokens = thinking_budget_tokens

        if not self.vertex_project_id:
            raise ValueError("VERTEX_PROJECT_ID environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Vertex AI API."""
        from google.cloud import aiplatform

        # Initialize Vertex AI
        aiplatform.init(
            project=self.vertex_project_id,
            location=self.vertex_region,
        )

        # This is a simplified implementation - actual Vertex AI streaming
        # requires more complex setup with proper authentication
        # For now, we'll use the Gemini handler as a fallback
        gemini_handler = GeminiHandler(
            gemini_api_key=self.vertex_api_key,
            gemini_model_id=self.vertex_model_id,
        )

        async for chunk in gemini_handler.create_message(system_prompt, messages, tools):
            yield chunk

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.vertex_model_id,
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
        return self.vertex_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class LmStudioHandler(ApiHandler):
    """LM Studio API handler with streaming support."""

    def __init__(
        self,
        lmstudio_base_url: str | None = None,
        lmstudio_model_id: str | None = None,
        lmstudio_max_tokens: int = 4000,
    ):
        self.lmstudio_base_url = lmstudio_base_url or os.getenv(
            "LMSTUDIO_BASE_URL", "http://localhost:1234"
        )
        self.lmstudio_model_id = lmstudio_model_id
        self.lmstudio_max_tokens = lmstudio_max_tokens

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using LM Studio API."""
        import aiohttp

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        payload = {
            "model": self.lmstudio_model_id,
            "messages": openai_messages,
            "temperature": 0.7,
            "max_tokens": self.lmstudio_max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.lmstudio_base_url}/v1/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"LM Studio API error: {response.status}")

                    async for line in response.content:
                        if line.strip():
                            try:
                                line_str = line.decode()
                                if line_str.startswith("data: "):
                                    chunk_data = json.loads(line_str[6:])

                                    if chunk_data.get("choices"):
                                        choice = chunk_data["choices"][0]
                                        if choice.get("delta", {}).get("content"):
                                            yield ApiStreamTextChunk(
                                                text=choice["delta"]["content"]
                                            )

                                        if choice.get("delta", {}).get("tool_calls"):
                                            for tool_call in choice["delta"]["tool_calls"]:
                                                yield ApiStreamToolCallsChunk(
                                                    tool_call={
                                                        "call_id": tool_call.get("id"),
                                                        "function": {
                                                            "id": tool_call.get("id"),
                                                            "name": tool_call.get(
                                                                "function", {}
                                                            ).get("name"),
                                                            "arguments": tool_call.get(
                                                                "function", {}
                                                            ).get("arguments"),
                                                        },
                                                    }
                                                )

                                        if chunk_data.get("usage"):
                                            usage = chunk_data["usage"]
                                            yield ApiStreamUsageChunk(
                                                input_tokens=usage.get("prompt_tokens", 0),
                                                output_tokens=usage.get("completion_tokens", 0),
                                            )
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            raise RuntimeError(f"LM Studio API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.lmstudio_model_id or "local-model",
            max_tokens=self.lmstudio_max_tokens,
            context_window=4096,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.0,
            output_price=0.0,
            temperature=0.7,
        )
        return self.lmstudio_model_id or "local-model", model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class DeepSeekHandler(ApiHandler):
    """DeepSeek API handler with streaming support."""

    def __init__(
        self,
        deepseek_api_key: str | None = None,
        deepseek_model_id: str = "deepseek-chat",
    ):
        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model_id = deepseek_model_id

        if not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using DeepSeek API."""
        client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=self.deepseek_api_key,
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.deepseek_model_id,
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
            raise RuntimeError(f"DeepSeek API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.deepseek_model_id,
            max_tokens=8000,
            context_window=128000,
            supports_images=False,
            supports_prompt_cache=True,
            input_price=0.0,
            output_price=1.1,
            cache_writes_price=0.27,
            cache_reads_price=0.07,
            temperature=1.0,
        )
        return self.deepseek_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class FireworksHandler(ApiHandler):
    """Fireworks AI API handler with streaming support."""

    def __init__(
        self,
        fireworks_api_key: str | None = None,
        fireworks_model_id: str = "accounts/fireworks/models/llama-v3p1-70b-instruct",
    ):
        self.fireworks_api_key = fireworks_api_key or os.getenv("FIREWORKS_API_KEY")
        self.fireworks_model_id = fireworks_model_id

        if not self.fireworks_api_key:
            raise ValueError("FIREWORKS_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Fireworks API."""
        client = OpenAI(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=self.fireworks_api_key,
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.fireworks_model_id,
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
                        )

        except Exception as e:
            raise RuntimeError(f"Fireworks API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.fireworks_model_id,
            max_tokens=8192,
            context_window=131072,
            supports_images=True,
            supports_prompt_cache=False,
            input_price=0.9,
            output_price=0.9,
            temperature=1.0,
        )
        return self.fireworks_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class TogetherHandler(ApiHandler):
    """Together AI API handler with streaming support."""

    def __init__(
        self,
        together_api_key: str | None = None,
        together_model_id: str = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    ):
        self.together_api_key = together_api_key or os.getenv("TOGETHER_API_KEY")
        self.together_model_id = together_model_id

        if not self.together_api_key:
            raise ValueError("TOGETHER_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Together API."""
        client = OpenAI(
            base_url="https://api.together.xyz/v1",
            api_key=self.together_api_key,
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.together_model_id,
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
                        )

        except Exception as e:
            raise RuntimeError(f"Together API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.together_model_id,
            max_tokens=8192,
            context_window=128000,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.9,
            output_price=0.9,
            temperature=1.0,
        )
        return self.together_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class QwenHandler(ApiHandler):
    """Qwen API handler with streaming support."""

    def __init__(
        self,
        qwen_api_key: str | None = None,
        qwen_model_id: str = "qwen-max",
    ):
        self.qwen_api_key = qwen_api_key or os.getenv("QWEN_API_KEY")
        self.qwen_model_id = qwen_model_id

        if not self.qwen_api_key:
            raise ValueError("QWEN_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Qwen API."""
        client = OpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self.qwen_api_key,
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.qwen_model_id,
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
                        )

        except Exception as e:
            raise RuntimeError(f"Qwen API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.qwen_model_id,
            max_tokens=30720,
            context_window=32768,
            supports_images=True,
            supports_prompt_cache=False,
            input_price=2.4,
            output_price=9.6,
            temperature=1.0,
        )
        return self.qwen_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class MistralHandler(ApiHandler):
    """Mistral API handler with streaming support."""

    def __init__(
        self,
        mistral_api_key: str | None = None,
        mistral_model_id: str = "mistral-large-latest",
    ):
        self.mistral_api_key = mistral_api_key or os.getenv("MISTRAL_API_KEY")
        self.mistral_model_id = mistral_model_id

        if not self.mistral_api_key:
            raise ValueError("MISTRAL_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Mistral API."""
        from mistralai import Mistral

        client = Mistral(api_key=self.mistral_api_key)

        # Convert messages to Mistral format
        mistral_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            mistral_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.stream(
                model=self.mistral_model_id,
                messages=mistral_messages,
                temperature=0.7,
                max_tokens=4000,
                tools=tools,
            )

            for chunk in stream:
                if chunk.data.choices and chunk.data.choices[0].delta:
                    delta = chunk.data.choices[0].delta

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

                    if chunk.data.usage:
                        yield ApiStreamUsageChunk(
                            input_tokens=chunk.data.usage.prompt_tokens or 0,
                            output_tokens=chunk.data.usage.completion_tokens or 0,
                        )

        except Exception as e:
            raise RuntimeError(f"Mistral API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.mistral_model_id,
            max_tokens=128000,
            context_window=128000,
            supports_images=True,
            supports_prompt_cache=False,
            input_price=2.0,
            output_price=6.0,
            temperature=0.7,
        )
        return self.mistral_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class HuggingFaceHandler(ApiHandler):
    """Hugging Face API handler with streaming support."""

    def __init__(
        self,
        huggingface_api_key: str | None = None,
        huggingface_model_id: str = "microsoft/DialoGPT-medium",
    ):
        self.huggingface_api_key = huggingface_api_key or os.getenv("HUGGINGFACE_API_KEY")
        self.huggingface_model_id = huggingface_model_id

        if not self.huggingface_api_key:
            raise ValueError("HUGGINGFACE_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Hugging Face API."""
        import aiohttp

        # Combine messages for Hugging Face format
        full_prompt = f"{system_prompt}\n\n"
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            full_prompt += f"{role.capitalize()}: {content}\n\n"

        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": 1000,
                "temperature": 0.7,
                "return_full_text": False,
            },
            "options": {
                "stream": True,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.huggingface_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api-inference.huggingface.co/models/{self.huggingface_model_id}",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Hugging Face API error: {response.status}")

                    async for line in response.content:
                        if line.strip():
                            try:
                                chunk_data = json.loads(line.decode())
                                if isinstance(chunk_data, list) and len(chunk_data) > 0:
                                    text = chunk_data[0].get("generated_text", "")
                                    if text:
                                        yield ApiStreamTextChunk(text=text)
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            raise RuntimeError(f"Hugging Face API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.huggingface_model_id,
            max_tokens=2048,
            context_window=2048,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.0,
            output_price=0.0,
            temperature=0.7,
        )
        return self.huggingface_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class LiteLlmHandler(ApiHandler):
    """LiteLLM API handler with streaming support."""

    def __init__(
        self,
        litellm_api_key: str | None = None,
        litellm_base_url: str | None = None,
        litellm_model_id: str = "gpt-3.5-turbo",
    ):
        self.litellm_api_key = litellm_api_key
        self.litellm_base_url = litellm_base_url
        self.litellm_model_id = litellm_model_id

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using LiteLLM proxy."""
        client = OpenAI(
            base_url=self.litellm_base_url or "http://localhost:4000",
            api_key=self.litellm_api_key or "dummy-key",
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.litellm_model_id,
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
                        )

        except Exception as e:
            raise RuntimeError(f"LiteLLM API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.litellm_model_id,
            max_tokens=4096,
            context_window=16384,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.0,
            output_price=0.0,
            temperature=0.7,
        )
        return self.litellm_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class MoonshotHandler(ApiHandler):
    """Moonshot API handler with streaming support."""

    def __init__(
        self,
        moonshot_api_key: str | None = None,
        moonshot_model_id: str = "moonshot-v1-8k",
    ):
        self.moonshot_api_key = moonshot_api_key or os.getenv("MOONSHOT_API_KEY")
        self.moonshot_model_id = moonshot_model_id

        if not self.moonshot_api_key:
            raise ValueError("MOONSHOT_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Moonshot API."""
        client = OpenAI(
            base_url="https://api.moonshot.cn/v1",
            api_key=self.moonshot_api_key,
        )

        # Convert messages to OpenAI format
        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            openai_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.moonshot_model_id,
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
                        )

        except Exception as e:
            raise RuntimeError(f"Moonshot API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.moonshot_model_id,
            max_tokens=3200,
            context_window=131072,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.012,
            output_price=0.012,
            temperature=0.3,
        )
        return self.moonshot_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass


class GroqHandler(ApiHandler):
    """Groq API handler with streaming support."""

    def __init__(
        self,
        groq_api_key: str | None = None,
        groq_model_id: str = "llama3-70b-8192",
    ):
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.groq_model_id = groq_model_id

        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable must be set")

    async def create_message(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ApiStream:
        """Create streaming message using Groq API."""
        from groq import Groq

        client = Groq(api_key=self.groq_api_key)

        # Convert messages to Groq format
        groq_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            groq_messages.append({"role": role, "content": content})

        try:
            stream = client.chat.completions.create(
                model=self.groq_model_id,
                messages=groq_messages,
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
                        )

        except Exception as e:
            raise RuntimeError(f"Groq API stream failed: {e}") from e

    def get_model(self) -> tuple[str, ModelInfo]:
        """Get current model info."""
        model_info = ModelInfo(
            name=self.groq_model_id,
            max_tokens=8192,
            context_window=8192,
            supports_images=False,
            supports_prompt_cache=False,
            input_price=0.59,
            output_price=0.79,
            temperature=0.7,
        )
        return self.groq_model_id, model_info

    def get_api_stream_usage(self) -> ApiStreamUsageChunk | None:
        """Get stream usage information."""
        return None

    def abort(self) -> None:
        """Abort current request."""
        pass
