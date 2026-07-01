from __future__ import annotations

import json
from pathlib import Path


def test_horde_provider_plugin_manifest_uses_single_provider_namespace():
    manifest_path = Path("addon/plugins/horde-provider/openclaw.plugin.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["id"] == "horde-provider"
    assert manifest["providers"] == ["horde-provider"]
    assert manifest["providerAuthChoices"][0]["provider"] == "horde-provider"
    assert "runtimeBridge" not in manifest["configSchema"]["properties"]


def test_horde_provider_package_declares_local_plugin_extension():
    package_path = Path("addon/plugins/horde-provider/package.json")
    package_json = json.loads(package_path.read_text(encoding="utf-8"))

    assert package_json["name"] == "@hordeforge/horde-provider"
    assert package_json["openclaw"]["providers"] == ["horde-provider"]
    assert package_json["openclaw"]["install"]["defaultChoice"] == "local"


def test_horde_provider_plugin_catalog_pins_qwen_compat_flags():
    index_path = Path("addon/plugins/horde-provider/index.ts")
    source = index_path.read_text(encoding="utf-8")

    assert "supportsDeveloperRole: false" in source
    assert "supportsUsageInStreaming: true" in source
    assert "supportsStrictMode: false" in source


def test_horde_provider_plugin_exposes_provider_chat_commands():
    index_path = Path("addon/plugins/horde-provider/index.ts")
    source = index_path.read_text(encoding="utf-8")

    assert 'name: "horde"' in source
    assert "provider add" in source
    assert "provider list" in source
    assert "provider remove" in source


def test_horde_provider_plugin_uses_native_oauth_hooks():
    index_path = Path("addon/plugins/horde-provider/index.ts")
    source = index_path.read_text(encoding="utf-8")

    assert "resolveExternalAuthProfiles" in source
    assert "refreshOAuth" in source
    assert "prepareRuntimeAuth" in source
    assert "wrapStreamFn" in source
    assert "DEFAULT_PORTAL_BASE_URL" in source
