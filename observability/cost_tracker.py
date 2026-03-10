from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any

# Default pricing for common model providers (USD per 1M tokens)
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "openai": {
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    },
    "anthropic": {
        "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-opus": {"input": 15.0, "output": 75.0},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
    },
    "google": {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
    },
    "generic": {
        "default": {"input": 1.0, "output": 2.0},
    },
}


@dataclass(slots=True)
class CostRecord:
    """Represents a single cost record for a model call."""

    run_id: str
    step_name: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    timestamp: str
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.cost_usd == 0.0:
            self.cost_usd = self.calculate_cost()

    def calculate_cost(self, pricing: dict[str, dict[str, float]] | None = None) -> float:
        """Calculate cost based on token counts and pricing."""
        effective_pricing = pricing or DEFAULT_PRICING

        provider_pricing = effective_pricing.get(self.provider, effective_pricing.get("generic", {}))
        model_pricing = provider_pricing.get(self.model, provider_pricing.get("default", {}))

        input_rate = model_pricing.get("input", 1.0)
        output_rate = model_pricing.get("output", 2.0)

        input_cost = (self.input_tokens / 1_000_000) * input_rate
        output_cost = (self.output_tokens / 1_000_000) * output_rate

        return round(input_cost + output_cost, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step_name": self.step_name,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_seconds": self.latency_seconds,
            "timestamp": self.timestamp,
            "cost_usd": self.cost_usd,
        }


@dataclass
class CostSummary:
    """Summary of costs for a run or pipeline."""

    run_id: str
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_calls: int
    by_model: dict[str, dict[str, Any]]
    by_step: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_calls": self.total_calls,
            "by_model": self.by_model,
            "by_step": self.by_step,
        }


class CostTracker:
    """Tracks costs for model calls within pipeline runs."""

    def __init__(
        self,
        *,
        budget_limit_usd: float | None = None,
        pricing: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.logger = logging.getLogger("hordeforge.cost")
        self._lock = RLock()
        self._records: list[CostRecord] = []
        self._budget_limit_usd = budget_limit_usd if budget_limit_usd and budget_limit_usd > 0 else None
        self._pricing = pricing or DEFAULT_PRICING

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_call(
        self,
        run_id: str,
        step_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_seconds: float = 0.0,
    ) -> CostRecord:
        """Record a model call and its associated costs."""
        record = CostRecord(
            run_id=run_id,
            step_name=step_name,
            provider=provider.lower(),
            model=model.lower(),
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            latency_seconds=max(0.0, latency_seconds),
            timestamp=self._utc_now_iso(),
        )
        # Recalculate cost with actual pricing
        record.cost_usd = record.calculate_cost(self._pricing)

        with self._lock:
            self._records.append(record)
            self._log_record(record)

        return record

    def _log_record(self, record: CostRecord) -> None:
        """Log cost record as JSON."""
        payload = record.to_dict()
        self.logger.info(json.dumps({"event": "cost_record", **payload}, ensure_ascii=False))

    def get_summary(self, run_id: str) -> CostSummary:
        """Get cost summary for a specific run."""
        with self._lock:
            run_records = [r for r in self._records if r.run_id == run_id]

        if not run_records:
            return CostSummary(
                run_id=run_id,
                total_cost_usd=0.0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_calls=0,
                by_model={},
                by_step={},
            )

        total_cost = sum(r.cost_usd for r in run_records)
        total_input = sum(r.input_tokens for r in run_records)
        total_output = sum(r.output_tokens for r in run_records)

        by_model: dict[str, dict[str, Any]] = {}
        for record in run_records:
            key = f"{record.provider}/{record.model}"
            if key not in by_model:
                by_model[key] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            by_model[key]["calls"] += 1
            by_model[key]["input_tokens"] += record.input_tokens
            by_model[key]["output_tokens"] += record.output_tokens
            by_model[key]["cost_usd"] += record.cost_usd

        by_step: dict[str, dict[str, Any]] = {}
        for record in run_records:
            if record.step_name not in by_step:
                by_step[record.step_name] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            by_step[record.step_name]["calls"] += 1
            by_step[record.step_name]["input_tokens"] += record.input_tokens
            by_step[record.step_name]["output_tokens"] += record.output_tokens
            by_step[record.step_name]["cost_usd"] += record.cost_usd

        return CostSummary(
            run_id=run_id,
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_calls=len(run_records),
            by_model=by_model,
            by_step=by_step,
        )

    def check_budget(self, run_id: str) -> tuple[bool, float]:
        """Check if run has exceeded budget limit."""
        if self._budget_limit_usd is None:
            return True, 0.0

        summary = self.get_summary(run_id)
        remaining = self._budget_limit_usd - summary.total_cost_usd
        return remaining >= 0, remaining

    def get_total_cost(self) -> float:
        """Get total cost across all tracked calls."""
        with self._lock:
            return sum(r.cost_usd for r in self._records)

    def clear(self) -> None:
        """Clear all records."""
        with self._lock:
            self._records.clear()

    def get_records(self, run_id: str | None = None) -> list[CostRecord]:
        """Get cost records, optionally filtered by run_id."""
        with self._lock:
            if run_id is None:
                return list(self._records)
            return [r for r in self._records if r.run_id == run_id]
