from __future__ import annotations

import pytest

pytest.importorskip("addon", reason="addon package not installed")

from addon.runtime.python.horde_provider.provision import build_gateway_provider_patch
from addon.runtime.python.horde_provider.schemas import HordeProviderResolvedAuth


def test_build_gateway_provider_patch_registers_model_without_overwriting_primary_model():
    resolved = HordeProviderResolvedAuth(
        profile_id="team:main",
        model="qwen3-coder-plus",
        model_ref="horde-provider/qwen3-coder-plus",
        api_key="access-token",
        base_url="https://portal.qwen.ai/v1",
        default_headers={"X-DashScope-AuthType": "qwen-oauth"},
    )

    patch = build_gateway_provider_patch(resolved, model_alias="horde")

    provider = patch["models"]["providers"]["horde-provider"]
    assert provider["api"] == "openai-completions"
    assert provider["apiKey"] == "access-token"
    assert provider["baseUrl"] == "https://portal.qwen.ai/v1"
    assert provider["models"][0]["id"] == "qwen3-coder-plus"
    assert provider["models"][0]["compat"] == {
        "supportsDeveloperRole": False,
        "supportsUsageInStreaming": True,
        "supportsStrictMode": False,
    }
    assert (
        patch["agents"]["defaults"]["models"]["horde-provider/qwen3-coder-plus"]["alias"] == "horde"
    )
    assert "model" not in patch["agents"]["defaults"]


def test_build_gateway_provider_patch_uses_runtime_bridge_url_when_provided():
    resolved = HordeProviderResolvedAuth(
        profile_id="team:main",
        model="qwen3-coder-plus",
        model_ref="horde-provider/qwen3-coder-plus",
        api_key="access-token",
        base_url="https://portal.qwen.ai/v1",
        default_headers={"X-DashScope-AuthType": "qwen-oauth"},
    )

    patch = build_gateway_provider_patch(
        resolved,
        model_alias="horde",
        runtime_base_url="http://host.docker.internal:8765/v1",
    )

    provider = patch["models"]["providers"]["horde-provider"]
    assert provider["baseUrl"] == "http://host.docker.internal:8765/v1"
    assert provider["headers"] == {}
