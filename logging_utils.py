from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "private_key",
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._+/=-]{8,}"),
)


def _is_sensitive_key(key: str | None) -> bool:
    if not key:
        return False
    key_lower = key.lower()
    return any(marker in key_lower for marker in SENSITIVE_MARKERS)


def _redact_string_value(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_sensitive_data(value: Any, key: str | None = None) -> Any:
    if _is_sensitive_key(key):
        return REDACTED

    if isinstance(value, dict):
        return {k: redact_sensitive_data(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item, key) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item, key) for item in value)
    if isinstance(value, str):
        return _redact_string_value(value)
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_sensitive_data(value, key) for key, value in data.items()}
