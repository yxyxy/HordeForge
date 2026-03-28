from __future__ import annotations

import pytest

from agents.llm_wrapper import (
    AnthropicWrapper,
    GoogleGenAIWrapper,
    OpenAIWrapper,
    build_code_prompt,
    build_spec_prompt,
    get_llm_wrapper,
)


def test_build_spec_prompt():
    """Test spec prompt building."""
    prompt = build_spec_prompt(
        summary="Test feature",
        requirements=["Req 1", "Req 2"],
        context={"key": "value"},
    )
    assert "Test feature" in prompt
    assert "Req 1" in prompt
    assert "Req 2" in prompt


def test_build_code_prompt():
    """Test code prompt building."""
    prompt = build_code_prompt(
        spec={"summary": "Test"},
        test_cases=[{"name": "test1"}],
        repo_context={"language": "python"},
    )
    assert "Test" in prompt
    assert "test1" in prompt


def test_get_llm_wrapper_unknown():
    """Test factory rejects unknown provider."""
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_wrapper("unknown")


def test_get_llm_wrapper_returns_none_for_empty():
    """Test factory returns None for empty provider."""
    result = get_llm_wrapper(None)
    assert result is None


def test_openai_wrapper_no_api_key():
    """Test OpenAI wrapper without API key."""
    wrapper = OpenAIWrapper(api_key="")
    with pytest.raises(RuntimeError, match="not available"):
        wrapper.complete("test prompt")


def test_anthropic_wrapper_no_api_key():
    """Test Anthropic wrapper without API key."""
    wrapper = AnthropicWrapper(api_key="")
    with pytest.raises(RuntimeError, match="not available"):
        wrapper.complete("test prompt")


def test_google_wrapper_no_api_key():
    """Test Google wrapper without API key."""
    wrapper = GoogleGenAIWrapper(api_key="")
    with pytest.raises(RuntimeError, match="not available"):
        wrapper.complete("test prompt")
