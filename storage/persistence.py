from __future__ import annotations

import json
import time
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


class JsonStore:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._lock = RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write_raw([])

    def _write_raw(self, payload: list[dict[str, Any]]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        temp_path = self.file_path.with_suffix(f"{self.file_path.suffix}.{uuid4().hex}.tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        last_error: OSError | None = None
        for attempt in range(5):
            try:
                temp_path.replace(self.file_path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.01 * (attempt + 1))
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                raw = self.file_path.read_text(encoding="utf-8").strip()
            except OSError:
                return []
            if not raw:
                return []
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return []
            if not isinstance(payload, list):
                return []
            return [item for item in payload if isinstance(item, dict)]

    def write_all(self, items: list[dict[str, Any]]) -> None:
        payload = [item for item in items if isinstance(item, dict)]
        with self._lock:
            self._write_raw(payload)
