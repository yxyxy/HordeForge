from __future__ import annotations

import json

import pytest

import agents.llm_wrapper as llm_wrapper_module
from agents.llm_wrapper import (
    AnthropicWrapper,
    GoogleGenAIWrapper,
    OpenAIWrapper,
    ProfileFallbackLLMWrapper,
    QwenCodeWrapper,
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
    original_candidates_loader = llm_wrapper_module._load_profile_candidates
    llm_wrapper_module._load_profile_defaults = lambda _=None: None
    llm_wrapper_module._load_profile_candidates = lambda _=None: []
    try:
        result = get_llm_wrapper(None)
    finally:
        llm_wrapper_module._load_profile_defaults = original_loader
        llm_wrapper_module._load_profile_candidates = original_candidates_loader
    assert result is None


def test_get_llm_wrapper_uses_profile_store_defaults(monkeypatch):
    """Test factory resolves provider/model/key from local profile store."""
    monkeypatch.setattr(llm_wrapper_module, "_load_profile_candidates", lambda _=None: [])
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


def test_get_llm_wrapper_uses_profile_fallback_when_multiple_profiles(monkeypatch):
    monkeypatch.setattr(
        llm_wrapper_module,
        "_load_profile_candidates",
        lambda _=None: [
            {
                "profile_name": "default",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "k1",
            },
            {"profile_name": "backup", "provider": "openai", "model": "gpt-4o", "api_key": "k2"},
        ],
    )
    monkeypatch.setattr(llm_wrapper_module, "_load_profile_defaults", lambda _=None: None)

    wrapper = get_llm_wrapper(None)

    assert isinstance(wrapper, ProfileFallbackLLMWrapper)


def test_profile_fallback_wrapper_tries_next_profile_on_failure(monkeypatch):
    class _FailWrapper:
        def complete(self, prompt: str, **kwargs):
            raise RuntimeError("failed profile")

        def complete_stream(self, prompt: str, **kwargs):
            raise RuntimeError("failed profile stream")

        def close(self):
            return None

    class _OkWrapper:
        def complete(self, prompt: str, **kwargs):
            return "ok-response"

        def complete_stream(self, prompt: str, **kwargs):
            yield "ok-stream"

        def close(self):
            return None

    wrappers = [_FailWrapper(), _OkWrapper()]

    original_get_llm_wrapper = llm_wrapper_module.get_llm_wrapper

    def _fake_get_llm_wrapper(provider=None, **kwargs):
        if provider:
            return wrappers.pop(0)
        return original_get_llm_wrapper(provider, **kwargs)

    monkeypatch.setattr(llm_wrapper_module, "get_llm_wrapper", _fake_get_llm_wrapper)

    wrapper = ProfileFallbackLLMWrapper(
        profile_candidates=[
            {"profile_name": "p1", "provider": "openai", "model": "m1", "api_key": "k1"},
            {"profile_name": "p2", "provider": "openai", "model": "m2", "api_key": "k2"},
        ]
    )

    assert wrapper.complete("hello") == "ok-response"


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


def test_qwen_wrapper_falls_back_to_stream_when_non_stream_fails(monkeypatch):
    class _Delta:
        def __init__(self, content: str):
            self.content = content

    class _Choice:
        def __init__(self, content: str):
            self.delta = _Delta(content)
            self.message = type("Message", (), {"content": content})()

    class _Chunk:
        def __init__(self, content: str):
            self.choices = [_Choice(content)]

    class _Completions:
        def create(self, **kwargs):
            if kwargs.get("stream"):
                return [_Chunk("hello "), _Chunk("world")]
            raise json.JSONDecodeError("Expecting value", "", 0)

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self):
            self.chat = _Chat()

    wrapper = QwenCodeWrapper(
        oauth_credentials_json=(
            '{"access_token":"x","refresh_token":"y","resource_url":"portal.qwen.ai",'
            '"expiry_date":9999999999999}'
        )
    )
    monkeypatch.setattr(wrapper, "_client", lambda: _Client())

    result = wrapper.complete("Say hello")

    assert result == "hello world"


def test_qwen_wrapper_uses_existing_token_when_refresh_returns_non_json(monkeypatch):
    class _DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_wrapper_module, "OpenAI", _DummyOpenAI)

    wrapper = QwenCodeWrapper(
        oauth_credentials_json=(
            '{"access_token":"x","refresh_token":"y","resource_url":"portal.qwen.ai",'
            '"expiry_date":1}'
        )
    )
    monkeypatch.setattr(
        wrapper._token_manager,  # noqa: SLF001
        "get_valid_credentials",
        lambda: (_ for _ in ()).throw(RuntimeError("non-JSON response")),
    )
    monkeypatch.setattr(
        wrapper._token_manager,  # noqa: SLF001
        "get_current_credentials",
        lambda: {
            "access_token": "x",
            "refresh_token": "y",
            "resource_url": "portal.qwen.ai",
            "expiry_date": 1,
        },
    )
    client = wrapper._client()

    assert isinstance(client, _DummyOpenAI)
    assert client.kwargs["api_key"] == "x"


def test_qwen_wrapper_sets_auth_cooldown_after_invalid_api_key(monkeypatch):
    class _Completions:
        def create(self, **kwargs):
            raise RuntimeError(
                "Error code: 401 - {'error': {'code': 'invalid_api_key', 'message': 'expired'}}"
            )

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self):
            self.chat = _Chat()

    wrapper = QwenCodeWrapper(
        oauth_credentials_json=(
            '{"access_token":"x","refresh_token":"y","resource_url":"portal.qwen.ai",'
            '"expiry_date":9999999999999}'
        )
    )
    wrapper._auth_failure_until_by_fingerprint.clear()

    called = {"count": 0}

    def _client():
        called["count"] += 1
        return _Client()

    monkeypatch.setattr(wrapper, "_client", _client)

    with pytest.raises(RuntimeError):
        wrapper.complete("test prompt")

    assert called["count"] == 1
    with pytest.raises(RuntimeError, match="auth cooldown"):
        wrapper.complete("test prompt")
    assert called["count"] == 1
