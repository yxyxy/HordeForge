from __future__ import annotations

import platform
import sys
from typing import Any


def resolve_base_url(credentials: dict[str, Any]) -> str:
    base_url = credentials.get("resource_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not isinstance(base_url, str) or not base_url:
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"https://{base_url}"
    if not base_url.endswith("/v1"):
        base_url = f"{base_url.rstrip('/')}/v1"
    return base_url


def build_dashscope_headers() -> dict[str, str]:
    platform_name = sys.platform
    if platform_name.startswith("win"):
        platform_name = "win32"
    elif platform_name == "darwin":
        platform_name = "darwin"
    else:
        platform_name = "linux"

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        machine = "x64"

    user_agent = f"QwenCode/0.0.0 ({platform_name}; {machine})"
    return {
        "User-Agent": user_agent,
        "X-DashScope-CacheControl": "enable",
        "X-DashScope-UserAgent": user_agent,
        "X-DashScope-AuthType": "qwen-oauth",
    }


def to_dashscope_content_parts(content: Any) -> list[dict[str, str]]:
    if isinstance(content, list):
        normalized: list[dict[str, str]] = []
        for item in content:
            if (
                isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ):
                normalized.append({"type": "text", "text": item["text"]})
        if normalized:
            return normalized
    text = content if isinstance(content, str) else str(content)
    return [{"type": "text", "text": text}]


def build_chat_messages(
    *,
    user_prompt: str,
    system_prompt: str = "",
) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": to_dashscope_content_parts(system_prompt)},
        {"role": "user", "content": to_dashscope_content_parts(user_prompt)},
    ]
