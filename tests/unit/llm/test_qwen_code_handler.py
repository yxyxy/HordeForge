from __future__ import annotations

import pytest

from agents.llm_providers import QwenCodeHandler


class _DummyTokenManager:
    def __init__(self, **_: object) -> None:
        pass

    def get_valid_credentials(self) -> dict[str, object]:
        return {
            "access_token": "test-access-token",
            "resource_url": "portal.qwen.ai",
        }

    def get_current_credentials(self) -> dict[str, object]:
        return self.get_valid_credentials()


@pytest.mark.asyncio
async def test_qwen_code_handler_sends_dashscope_headers_and_content_parts(monkeypatch):
    captured: dict[str, object] = {}

    class _DummyCompletions:
        def create(self, **kwargs):
            captured["request_kwargs"] = kwargs
            return []

    class _DummyChat:
        def __init__(self) -> None:
            self.completions = _DummyCompletions()

    class _DummyOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = _DummyChat()

    import agents.llm_providers as providers_module
    import agents.qwen_oauth_token_manager as oauth_module

    monkeypatch.setattr(oauth_module, "QwenOAuthTokenManager", _DummyTokenManager)
    monkeypatch.setattr(providers_module, "OpenAI", _DummyOpenAI)

    handler = QwenCodeHandler(
        qwen_oauth_credentials_json='{"refresh_token": "test-refresh-token"}',
        qwen_model_id="coder-model",
    )

    stream = handler.create_message(
        "You are helpful.",
        [{"role": "user", "content": "ping"}],
        tools=None,
    )
    async for _ in stream:
        pass

    client_kwargs = captured["client_kwargs"]
    assert client_kwargs["base_url"] == "https://portal.qwen.ai/v1"
    assert client_kwargs["api_key"] == "test-access-token"
    assert client_kwargs["default_headers"]["X-DashScope-CacheControl"] == "enable"
    assert client_kwargs["default_headers"]["X-DashScope-AuthType"] == "qwen-oauth"
    assert "User-Agent" in client_kwargs["default_headers"]
    assert "X-DashScope-UserAgent" in client_kwargs["default_headers"]

    request_kwargs = captured["request_kwargs"]
    assert request_kwargs["model"] == "coder-model"
    assert request_kwargs["stream"] is True
    assert request_kwargs["messages"] == [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are helpful."}],
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "ping"}],
        },
    ]
