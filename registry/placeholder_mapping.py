from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_CONTRACT_MAP: dict[str, str] = {
    "dod": "context.dod.v1",
    "specification": "context.spec.v1",
    "feature_spec": "context.spec.v1",
    "tests": "context.tests.v1",
    "code_patch": "context.code_patch.v1",
    "fixed_code_patch": "context.code_patch.v1",
    "final_code_patch": "context.code_patch.v1",
}

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def extract_placeholders(value: Any) -> list[str]:
    """Extract placeholders like {{name}} from nested values."""
    if isinstance(value, str):
        return _PLACEHOLDER_PATTERN.findall(value)
    if isinstance(value, dict):
        refs: list[str] = []
        for item in value.values():
            refs.extend(extract_placeholders(item))
        return refs
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(extract_placeholders(item))
        return refs
    return []


def root_key(path: str) -> str:
    """Extract the root key from a dotted placeholder path."""
    return str(path).strip().split(".", maxsplit=1)[0]


def resolve_contract_for_key(key: str) -> str | None:
    """Resolve contract name for a placeholder root key."""
    return PLACEHOLDER_CONTRACT_MAP.get(key)


def resolve_contract_for_placeholder(placeholder: str) -> str | None:
    """Resolve contract name for a full placeholder path."""
    return resolve_contract_for_key(root_key(placeholder))
