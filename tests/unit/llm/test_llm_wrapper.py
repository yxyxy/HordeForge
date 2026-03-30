from __future__ import annotations

import pytest

import agents.llm_wrapper as llm_wrapper_module
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
    """Test factory returns None for empty provider when no defaults configured."""
    llm_wrapper_module.os.environ.pop("HORDEFORGE_LLM_PROFILE", None)
    original_loader = llm_wrapper_module._load_profile_defaults
    llm_wrapper_module._load_profile_defaults = lambda _=None: None
    try:
        result = get_llm_wrapper(None)
    finally:
        llm_wrapper_module._load_profile_defaults = original_loader
    assert result is None


def test_get_llm_wrapper_uses_profile_store_defaults(monkeypatch):
    """Test factory resolves provider/model/key from local profile store."""
    monkeypatch.setattr(
        llm_wrapper_module,
        "_load_profile_defaults",
        lambda _=None: {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "profile-api-key",
            "base_url": None,
        },
    )
    monkeypatch.delenv("HORDEFORGE_LLM_PROFILE", raising=False)
    result = get_llm_wrapper(None)
    assert isinstance(result, OpenAIWrapper)
    assert result._model == "gpt-4o-mini"
    assert result._api_key == "profile-api-key"


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
