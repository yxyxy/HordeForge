from __future__ import annotations

import re
from typing import Any


def snapshot_mapping_items(value: dict[Any, Any]) -> list[tuple[Any, Any]]:
    """Take a best-effort snapshot of dict items even under concurrent mutation."""
    for _ in range(3):
        try:
            return list(value.items())
        except RuntimeError as exc:
            if "dictionary changed size during iteration" not in str(exc):
                raise
    return []


def resolve_path(source: dict[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted path like 'key.subkey.array[0].field' from source dict."""
    current: Any = source
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            # Try to handle array access like items[0]
            if "[" in part and "]" in part:
                key, idx_str = part.split("[")
                idx = int(idx_str.rstrip("]"))
                if isinstance(current, dict) and key in current:
                    arr = current[key]
                    if isinstance(arr, list) and 0 <= idx < len(arr):
                        current = arr[idx]
                        continue
            return None
        current = current[part]
    return current


def extract_error_line(text: str) -> str:
    """Extract the first meaningful error line from test output."""
    if not isinstance(text, str) or not text.strip():
        return ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("E       "):
            return line[len("E       ") :].strip()
        if line.startswith("E   "):
            return line[len("E   ") :].strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):\s+", line):
            return line
    return ""
