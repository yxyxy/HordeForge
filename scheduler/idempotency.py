from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any


def build_payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_idempotency_key(*, source: str, pipeline_name: str, payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        {
            "source": source,
            "pipeline_name": pipeline_name,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"hf:{digest}"


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._mapping: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _prune(self) -> None:
        now = self._now()
        expired = [
            key
            for key, value in self._mapping.items()
            if isinstance(value.get("expires_at"), datetime) and value["expires_at"] <= now
        ]
        for key in expired:
            self._mapping.pop(key, None)

    def remember(self, key: str, run_id: str, result: dict[str, Any] | None = None) -> None:
        self._prune()
        self._mapping[key] = {
            "run_id": run_id,
            "result": result or {},
            "created_at": self._now(),
            "expires_at": self._now() + timedelta(seconds=self.ttl_seconds),
        }

    def get(self, key: str) -> dict[str, Any] | None:
        self._prune()
        value = self._mapping.get(key)
        if value is None:
            return None
        return {
            "run_id": value["run_id"],
            "result": value["result"],
            "created_at": value["created_at"].isoformat(),
            "expires_at": value["expires_at"].isoformat(),
        }

    def clear(self) -> None:
        self._mapping.clear()
