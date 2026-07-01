from __future__ import annotations

import pytest

from agents.qwen_oauth_token_manager import QwenOAuthTokenManager


@pytest.fixture(autouse=True)
def isolate_qwen_oauth_manager_state():
    QwenOAuthTokenManager._memory_cache.clear()
    QwenOAuthTokenManager._refresh_locks.clear()
    yield
    QwenOAuthTokenManager._memory_cache.clear()
    QwenOAuthTokenManager._refresh_locks.clear()
