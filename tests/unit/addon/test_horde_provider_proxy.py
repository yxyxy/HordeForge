from __future__ import annotations

import pytest

pytest.importorskip("addon", reason="addon package not installed")

from addon.runtime.python.horde_provider.proxy import (
    build_portal_payload,
    flatten_message_text,
)


def test_flatten_message_text_collects_text_blocks():
    assert (
        flatten_message_text(
            [
                {"type": "text", "text": "alpha"},
                {"type": "ignored", "text": "skip"},
                {"type": "text", "text": "beta"},
            ]
        )
        == "alpha\nbeta"
    )


def test_build_portal_payload_normalizes_openclaw_payload_for_qwen_portal():
    payload = build_portal_payload(
        {
            "model": "qwen3-coder-plus",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Reply with OK only."}]},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
            "tools": [{"type": "function", "function": {"name": "message"}}],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "response_format": {"type": "json_object"},
        },
        default_system_prompt="You are a concise assistant.",
        default_max_completion_tokens=512,
    )

    assert payload == {
        "model": "qwen3-coder-plus",
        "messages": [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Reply with OK only."},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "store": False,
        "max_completion_tokens": 512,
        "reasoning_effort": "high",
    }


def test_build_portal_payload_preserves_existing_system_and_assistant_turns():
    payload = build_portal_payload(
        {
            "model": "qwen3-coder-plus",
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "System prompt"}]},
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": [{"type": "text", "text": "Second"}]},
                {"role": "tool", "content": "ignored"},
                {"role": "user", "content": [{"type": "text", "text": "Third"}]},
            ],
            "stream": False,
            "max_completion_tokens": 64,
            "reasoning_effort": "medium",
        },
        default_system_prompt="fallback",
        default_max_completion_tokens=512,
    )

    assert payload["messages"] == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Second"},
        {"role": "user", "content": "Third"},
    ]
    assert payload["stream"] is False
    assert payload["max_completion_tokens"] == 64
    assert payload["reasoning_effort"] == "medium"


def test_build_portal_payload_replaces_oversized_system_prompt():
    payload = build_portal_payload(
        {
            "model": "qwen3-coder-plus",
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "OpenClaw bootstrap " * 600}],
                },
                {"role": "user", "content": "Reply with OK only."},
            ],
            "stream": False,
        },
        default_system_prompt="You are a concise assistant.",
        default_max_completion_tokens=512,
    )

    assert payload["messages"][0] == {
        "role": "system",
        "content": "You are a concise assistant.",
    }
