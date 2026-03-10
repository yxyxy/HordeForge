from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import jsonschema
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


class OpenAIWrapper(LLMWrapper):
    """OpenAI API wrapper using Responses API (not legacy Chat Completions)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None

    def _get_api_key_from_env(self) -> str:
        return os.getenv("HORDEFORGE_OPENAI_API_KEY", "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(
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
            raise RuntimeError("OpenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = self._apply_retry(
                client.responses.create,
                model=model,
                input=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=max_tokens,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}") from e

        if not response.output or not response.output[0].content:
            raise RuntimeError("Empty response from OpenAI API")

        # Handle different content types
        content = response.output[0].content
        if hasattr(content, "text"):
            return content.text
        return str(content)

    def complete_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Streaming completion using OpenAI Responses API."""
        client = self._get_client()
        if client is None:
            raise RuntimeError("OpenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            stream = client.responses.create(
                model=model,
                input=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=max_tokens,
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API stream failed: {e}") from e

        for event in stream:
            if event.type == "response.output_text.delta":
                if hasattr(event.delta, "text"):
                    yield event.delta.text

    def close(self) -> None:
        self._client = None


class AnthropicWrapper(LLMWrapper):
    """Anthropic Claude API wrapper with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None

    def _get_api_key_from_env(self) -> str:
        return os.getenv("HORDEFORGE_ANTHROPIC_API_KEY", "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import anthropic

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

    def close(self) -> None:
        self._client = None


class GoogleGenAIWrapper(LLMWrapper):
    """Google Gemini API wrapper with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        super().__init__(api_key, model, timeout, max_retries)
        self._client = None

    def _get_api_key_from_env(self) -> str:
        return os.getenv("HORDEFORGE_GOOGLE_API_KEY", "")

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import google.genai as genai

                genai.configure(api_key=self._api_key)
                self._client = genai
            except ImportError:
                pass
        return self._client

    def complete(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Google GenAI client not available. Check API key.")

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            response = self._apply_retry(
                client.models.generate_content,
                model=model,
                contents=prompt,
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

        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 4000)

        try:
            stream = client.models.generate_content(
                model=model,
                contents=prompt,
                generation_config={
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_output_tokens": max_tokens,
                },
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"Google GenAI API stream failed: {e}") from e

        for chunk in stream:
            if chunk.text:
                yield chunk.text

    def close(self) -> None:
        self._client = None


def get_llm_wrapper(
    provider: str | None = None,
    **kwargs,
) -> LLMWrapper | None:
    """Factory to get LLM wrapper."""
    provider = provider or os.getenv("HORDEFORGE_LLM_PROVIDER", "").lower()

    if provider == "openai":
        return OpenAIWrapper(**kwargs)
    elif provider == "anthropic":
        return AnthropicWrapper(**kwargs)
    elif provider == "google":
        return GoogleGenAIWrapper(**kwargs)
    elif provider:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return None


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
            raise ValueError(
                f"Unknown task: {task}. "
                f"Available: {list(self._routing.keys())}"
            )

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
            raise RuntimeError(
                f"No LLM provider available for task: {task}"
            )

        # Cache the wrapper
        self._cache[task] = wrapper
        logger.info(
            f"Routed task '{task}' to {provider}/{model}: {config['description']}"
        )

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
                    "test_criteria": {"type": "string", "description": "How to verify this requirement"},
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

    # JSON Schema validation (strict validation for production)
    if validate_schema:
        try:
            jsonschema.validate(spec, SPEC_OUTPUT_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Schema validation failed: {e.message} at {'.'.join(str(p) for p in e.path)}") from e

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
- Style: {standards['style']}
- Typing: {standards['typing']}
- Docstrings: {standards['docstrings']}
- Imports: {standards['imports']}

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
