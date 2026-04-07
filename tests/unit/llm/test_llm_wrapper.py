from __future__ import annotations

import json

import pytest
import requests

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


def test_load_profile_defaults_uses_gateway_profile_field(monkeypatch):
    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "profile": {
                    "profile_name": "qwen-code",
                    "provider": "qwen-code",
                    "model": "coder-model",
                    "base_url": None,
                    "api_key_ref": "llm.qwen-code.api_key",
                }
            }

    monkeypatch.setenv("HORDEFORGE_GATEWAY_URL", "http://gw.test")
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(
        llm_wrapper_module,
        "_load_secret_with_gateway_fallback",
        lambda _key: "token-json",
    )

    loaded = llm_wrapper_module._load_profile_defaults("qwen-code")

    assert loaded is not None
    assert loaded["provider"] == "qwen-code"
    assert loaded["model"] == "coder-model"
    assert loaded["api_key"] == "token-json"


def test_load_profile_candidates_prefers_gateway(monkeypatch):
    def _fake_get(url: str, params=None, **kwargs):
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                if params and params.get("profile_name") == "qwen-code":
                    return {
                        "profile": {
                            "profile_name": "qwen-code",
                            "provider": "qwen-code",
                            "model": "coder-model",
                            "base_url": None,
                            "api_key_ref": "llm.qwen-code.api_key",
                        }
                    }
                return {
                    "profiles": [
                        {
                            "profile_name": "qwen-code",
                            "provider": "qwen-code",
                            "model": "coder-model",
                            "base_url": None,
                            "api_key_ref": "llm.qwen-code.api_key",
                            "is_default": True,
                        }
                    ]
                }

        return _Resp()

    monkeypatch.setenv("HORDEFORGE_GATEWAY_URL", "http://gw.test")
    monkeypatch.setattr(requests, "get", _fake_get)
    monkeypatch.setattr(
        llm_wrapper_module,
        "_load_secret_with_gateway_fallback",
        lambda _key: "token-json",
    )

    candidates = llm_wrapper_module._load_profile_candidates("qwen-code")

    assert len(candidates) == 1
    assert candidates[0]["provider"] == "qwen-code"
    assert candidates[0]["model"] == "coder-model"


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


def test_profile_fallback_qwen_refresh_does_not_force_refresh():
    class _TokenManager:
        def __init__(self):
            self.calls: list[tuple[tuple, dict]] = []

        def get_valid_credentials(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"access_token": "ok"}

    class _Wrapper:
        def __init__(self):
            self._token_manager = _TokenManager()
            self._model = "coder-model"

    wrapper = _Wrapper()
    ProfileFallbackLLMWrapper._try_refresh_qwen_oauth(wrapper)
    calls = wrapper._token_manager.calls
    assert len(calls) == 1
    assert calls[0][0] == ()
    assert calls[0][1] == {}


def test_profile_fallback_qwen_refresh_failure_does_not_log_access_token(caplog):
    secret_token = "secret_access_token_value"

    class _TokenManager:
        def get_valid_credentials(self, *args, **kwargs):
            raise RuntimeError("refresh failed")

        def get_current_credentials(self):
            return {"access_token": secret_token}

    class _Wrapper:
        def __init__(self):
            self._token_manager = _TokenManager()
            self._model = "coder-model"

    caplog.set_level("WARNING")
    ProfileFallbackLLMWrapper._try_refresh_qwen_oauth(_Wrapper())
    assert "llm_profile_qwen_oauth_refresh_failed" in caplog.text
    assert "refresh failed" in caplog.text
    assert secret_token not in caplog.text


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


def test_anthropic_model_info_has_consistent_token_limits():
    wrapper = AnthropicWrapper(api_key="test-key")
    _, model_info = wrapper.get_model()

    assert isinstance(model_info.max_tokens, int)
    assert isinstance(model_info.context_window, int)
    assert model_info.context_window >= model_info.max_tokens


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
    wrapper._auth_failure_until_by_fingerprint.clear()
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


def test_qwen_wrapper_sends_dashscope_headers_and_content_parts(monkeypatch):
    captured_client_kwargs: dict[str, object] = {}
    captured_create_kwargs: dict[str, object] = {}

    class _ResponseChoice:
        def __init__(self):
            self.message = type("Message", (), {"content": "ok"})()

    class _Response:
        def __init__(self):
            self.choices = [_ResponseChoice()]

    class _Completions:
        def create(self, **kwargs):
            captured_create_kwargs.clear()
            captured_create_kwargs.update(kwargs)
            return _Response()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _DummyOpenAI:
        def __init__(self, **kwargs):
            captured_client_kwargs.clear()
            captured_client_kwargs.update(kwargs)
            self.chat = _Chat()

    monkeypatch.setattr(llm_wrapper_module, "OpenAI", _DummyOpenAI)

    wrapper = QwenCodeWrapper(
        oauth_credentials_json=(
            '{"access_token":"x","refresh_token":"y","resource_url":"portal.qwen.ai",'
            '"expiry_date":9999999999999}'
        ),
        model="coder-model",
    )

    wrapper.complete("Hello", max_retries=1, max_tokens=64, temperature=0.1)

    assert captured_client_kwargs["base_url"] == "https://portal.qwen.ai/v1"
    default_headers = captured_client_kwargs.get("default_headers")
    assert isinstance(default_headers, dict)
    assert default_headers["X-DashScope-AuthType"] == "qwen-oauth"
    assert default_headers["X-DashScope-CacheControl"] == "enable"

    messages = captured_create_kwargs["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == [{"type": "text", "text": "Hello"}]


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


def test_qwen_wrapper_retries_on_empty_body_and_succeeds(monkeypatch):
    QwenCodeWrapper._auth_failure_until_by_fingerprint.clear()

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

    class _Response:
        def __init__(self, content: str):
            self.choices = [_Choice(content)]

    class _Completions:
        def __init__(self):
            self.stream_calls = 0
            self.non_stream_calls = 0

        def create(self, **kwargs):
            if kwargs.get("stream"):
                self.stream_calls += 1
                if self.stream_calls == 1:
                    return [_Chunk("")]
                return [_Chunk("ok"), _Chunk("-after-retry")]
            self.non_stream_calls += 1
            return _Response("")

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
    monkeypatch.setattr(llm_wrapper_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_wrapper_module.random, "uniform", lambda _a, _b: 0.0)

    result = wrapper.complete("test prompt")

    assert result == "ok-after-retry"


def test_qwen_wrapper_does_not_retry_on_http_401_and_logs_diagnostics(monkeypatch, caplog):
    QwenCodeWrapper._auth_failure_until_by_fingerprint.clear()

    class _FakeResponse:
        status_code = 401
        headers = {
            "content-type": "application/json",
            "x-request-id": "req-401",
        }
        text = '{"error":{"code":"invalid_api_key"}}'

    class _FakeError(Exception):
        def __init__(self):
            super().__init__("Error code: 401 - invalid access token")
            self.status_code = 401
            self.request_id = "req-401"
            self.response = _FakeResponse()

    class _Completions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise _FakeError()

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
    client = _Client()
    monkeypatch.setattr(wrapper, "_client", lambda: client)
    monkeypatch.setattr(llm_wrapper_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_wrapper_module.random, "uniform", lambda _a, _b: 0.0)

    caplog.set_level("WARNING")
    with pytest.raises(RuntimeError):
        wrapper.complete("test prompt")

    assert client.chat.completions.calls == 2
    assert "qwen_llm_retry_scheduled" not in caplog.text
    assert "status_code=401" in caplog.text
    assert "request_id=req-401" in caplog.text
