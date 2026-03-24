from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime

from .llm_wrapper import ModelInfo

logger = logging.getLogger(__name__)


@dataclass
class PriceTier:
    """Price tier for tiered pricing model - Cline compatible."""

    tokenLimit: int  # Upper limit (inclusive) of input tokens for this tier - Cline naming
    price: float  # Price per million tokens for this tier
    inputPrice: float | None = None  # Cline naming
    outputPrice: float | None = None  # Cline naming
    cacheWritesPrice: float | None = None  # Cline naming
    cacheReadsPrice: float | None = None  # Cline naming

    # Backward compatibility properties
    @property
    def token_limit(self) -> int:
        return self.tokenLimit


@dataclass
class TokenUsage:
    """Track token usage for cost calculation - Cline compatible."""

    inputTokens: int = 0  # Cline naming
    outputTokens: int = 0  # Cline naming
    cacheWriteTokens: int = 0  # Cline naming
    cacheReadTokens: int = 0  # Cline naming
    thoughtsTokenCount: int = 0  # Cline naming
    reasoningTokens: int = 0  # Additional reasoning tokens tracking
    reasoningTimeMs: int = 0  # Reasoning time in milliseconds
    cacheCreationInputTokens: int = 0  # Cache creation tokens
    cacheReadInputTokens: int = 0  # Cache read tokens

    def total_tokens(self) -> int:
        return (
            self.inputTokens
            + self.outputTokens
            + self.cacheWriteTokens
            + self.cacheReadTokens
            + self.thoughtsTokenCount
            + self.reasoningTokens
        )

    def add(self, other: TokenUsage) -> TokenUsage:
        """Add another TokenUsage to this one."""
        self.inputTokens += other.inputTokens
        self.outputTokens += other.outputTokens
        self.cacheWriteTokens += other.cacheWriteTokens
        self.cacheReadTokens += other.cacheReadTokens
        self.thoughtsTokenCount += other.thoughtsTokenCount
        self.reasoningTokens += other.reasoningTokens
        self.reasoningTimeMs += other.reasoningTimeMs
        self.cacheCreationInputTokens += other.cacheCreationInputTokens
        self.cacheReadInputTokens += other.cacheReadInputTokens
        return self

    # Backward compatibility properties
    @property
    def input_tokens(self) -> int:
        return self.inputTokens

    @property
    def output_tokens(self) -> int:
        return self.outputTokens

    @property
    def cache_write_tokens(self) -> int:
        return self.cacheWriteTokens

    @property
    def cache_read_tokens(self) -> int:
        return self.cacheReadTokens

    @property
    def thoughts_token_count(self) -> int:
        return self.thoughtsTokenCount


@dataclass
class CostBreakdown:
    """Detailed cost breakdown - Cline compatible."""

    inputCost: float = 0.0  # Cline naming
    outputCost: float = 0.0  # Cline naming
    cacheWriteCost: float = 0.0  # Cline naming
    cacheReadCost: float = 0.0  # Cline naming
    thoughtsCost: float = 0.0  # Cline naming
    reasoningCost: float = 0.0  # Additional reasoning cost
    totalCost: float = 0.0  # Cline naming
    totalTokens: int = 0  # Total tokens processed
    totalInputTokens: int = 0  # Total input tokens
    totalOutputTokens: int = 0  # Total output tokens

    def add(self, other: CostBreakdown) -> CostBreakdown:
        """Add another CostBreakdown to this one."""
        self.inputCost += other.inputCost
        self.outputCost += other.outputCost
        self.cacheWriteCost += other.cacheWriteCost
        self.cacheReadCost += other.cacheReadCost
        self.thoughtsCost += other.thoughtsCost
        self.reasoningCost += other.reasoningCost
        self.totalCost += other.totalCost
        self.totalTokens += other.totalTokens
        self.totalInputTokens += other.totalInputTokens
        self.totalOutputTokens += other.totalOutputTokens
        return self

    # Backward compatibility properties with setters
    @property
    def input_cost(self) -> float:
        return self.inputCost

    @input_cost.setter
    def input_cost(self, value: float) -> None:
        self.inputCost = value

    @property
    def output_cost(self) -> float:
        return self.outputCost

    @output_cost.setter
    def output_cost(self, value: float) -> None:
        self.outputCost = value

    @property
    def cache_write_cost(self) -> float:
        return self.cacheWriteCost

    @cache_write_cost.setter
    def cache_write_cost(self, value: float) -> None:
        self.cacheWriteCost = value

    @property
    def cache_read_cost(self) -> float:
        return self.cacheReadCost

    @cache_read_cost.setter
    def cache_read_cost(self, value: float) -> None:
        self.cacheReadCost = value

    @property
    def thoughts_cost(self) -> float:
        return self.thoughtsCost

    @thoughts_cost.setter
    def thoughts_cost(self, value: float) -> None:
        self.thoughtsCost = value

    @property
    def total_cost(self) -> float:
        return self.totalCost

    @total_cost.setter
    def total_cost(self, value: float) -> None:
        self.totalCost = value


@dataclass
class BudgetLimits:
    """Budget limits for spending control - Cline compatible."""

    dailyLimit: float | None = None  # Cline naming
    monthlyLimit: float | None = None  # Cline naming
    sessionLimit: float | None = None  # Cline naming
    reasoningBudgetTokens: int | None = None  # For models that support reasoning - Cline naming
    totalLimit: float | None = None  # Total lifetime limit
    requestLimit: int | None = None  # Per-request token limit

    # Support both snake_case and camelCase initialization
    def __init__(
        self,
        dailyLimit: float | None = None,
        monthlyLimit: float | None = None,
        sessionLimit: float | None = None,
        reasoningBudgetTokens: int | None = None,
        totalLimit: float | None = None,
        requestLimit: int | None = None,
        # Snake case variants for backward compatibility
        daily_limit: float | None = None,
        monthly_limit: float | None = None,
        session_limit: float | None = None,
        reasoning_budget_tokens: int | None = None,
        total_limit: float | None = None,
        request_limit: int | None = None,
    ):
        # Prefer snake_case if provided (for backward compatibility)
        self.dailyLimit = daily_limit if daily_limit is not None else dailyLimit
        self.monthlyLimit = monthly_limit if monthly_limit is not None else monthlyLimit
        self.sessionLimit = session_limit if session_limit is not None else sessionLimit
        self.reasoningBudgetTokens = (
            reasoning_budget_tokens
            if reasoning_budget_tokens is not None
            else reasoningBudgetTokens
        )
        self.totalLimit = total_limit if total_limit is not None else totalLimit
        self.requestLimit = request_limit if request_limit is not None else requestLimit

    # Backward compatibility properties
    @property
    def daily_limit(self) -> float | None:
        return self.dailyLimit

    @property
    def monthly_limit(self) -> float | None:
        return self.monthlyLimit

    @property
    def session_limit(self) -> float | None:
        return self.sessionLimit

    @property
    def reasoning_budget_tokens(self) -> int | None:
        return self.reasoningBudgetTokens


class TokenBudgetSystem:
    """System for tracking token usage and costs with budget limits."""

    def __init__(self, budget_limits: BudgetLimits | None = None):
        self.budget_limits = budget_limits or BudgetLimits()
        self.daily_usage: dict[str, TokenUsage] = {}  # provider -> usage
        self.monthly_usage: dict[str, TokenUsage] = {}
        self.session_usage: dict[str, TokenUsage] = {}
        self.total_cost = 0.0
        self.lock = threading.Lock()

        # Load historical data
        self.load_usage_data()

    def calculate_cost(self, model_info: ModelInfo, usage: TokenUsage) -> CostBreakdown:
        """Calculate cost based on model info and usage - Cline compatible."""
        breakdown = CostBreakdown()
        breakdown.totalTokens = usage.total_tokens()
        breakdown.totalInputTokens = usage.input_tokens
        breakdown.totalOutputTokens = usage.output_tokens

        # Apply tiered pricing if available
        if model_info.tiers:
            # Find appropriate tier based on input tokens
            tier = None
            for t in sorted(model_info.tiers, key=lambda x: x.get("contextWindow", 0)):
                if usage.input_tokens <= t.get("contextWindow", float("inf")):
                    tier = t
                    break

            if tier:
                # Use tier-specific pricing
                input_price = tier.get("inputPrice", model_info.input_price)
                output_price = tier.get("outputPrice", model_info.output_price)
                cache_write_price = tier.get("cacheWritesPrice", model_info.cache_writes_price)
                cache_read_price = tier.get("cacheReadsPrice", model_info.cache_reads_price)

                if input_price is not None:
                    breakdown.input_cost = (
                        usage.input_tokens / 1_000
                    ) * input_price  # For tiered pricing, divide by 1K
                if output_price is not None:
                    breakdown.output_cost = (usage.output_tokens / 1_000_000) * output_price
                if cache_read_price is not None:
                    breakdown.cache_read_cost = (
                        usage.cache_read_tokens / 1_000_000
                    ) * cache_read_price
                if cache_write_price is not None:
                    breakdown.cache_write_cost = (
                        usage.cache_write_tokens / 1_000_000
                    ) * cache_write_price
        else:
            # Use flat pricing from model info
            if model_info.input_price is not None:
                breakdown.input_cost = (usage.input_tokens / 1_000_000) * model_info.input_price
            if model_info.output_price is not None:
                breakdown.output_cost = (usage.output_tokens / 1_000) * model_info.output_price
            if model_info.cache_reads_price is not None:
                breakdown.cache_read_cost = (
                    usage.cache_read_tokens / 1_000_000
                ) * model_info.cache_reads_price
            if model_info.cache_writes_price is not None:
                breakdown.cache_write_cost = (
                    usage.cache_write_tokens / 1_000_000
                ) * model_info.cache_writes_price

        # Handle reasoning costs if specified in thinking_config
        if model_info.thinking_config:
            reasoning_output_price = model_info.thinking_config.get(
                "outputPrice", model_info.output_price or 0
            )
            breakdown.thoughts_cost = (usage.thoughts_token_count / 1_000) * reasoning_output_price
            # Also handle reasoning tokens separately if present
            if hasattr(usage, "reasoningTokens") and usage.reasoningTokens > 0:
                breakdown.reasoningCost = (
                    usage.reasoningTokens / 1_000_000
                ) * reasoning_output_price

        breakdown.total_cost = (
            breakdown.input_cost
            + breakdown.output_cost
            + breakdown.cache_write_cost
            + breakdown.cache_read_cost
            + breakdown.thoughts_cost
            + breakdown.reasoningCost
        )

        return breakdown

    def track_usage(self, provider: str, model_info: ModelInfo, usage: TokenUsage) -> CostBreakdown:
        """Track token usage and calculate costs."""
        with self.lock:
            # Calculate cost
            cost_breakdown = self.calculate_cost(model_info, usage)

            # Update usage tracking
            today = datetime.now().strftime("%Y-%m-%d")
            month = datetime.now().strftime("%Y-%m")

            # Daily usage
            if today not in self.daily_usage:
                self.daily_usage[today] = {}
            if provider not in self.daily_usage[today]:
                self.daily_usage[today][provider] = TokenUsage()
            self.daily_usage[today][provider].add(usage)

            # Monthly usage
            if month not in self.monthly_usage:
                self.monthly_usage[month] = {}
            if provider not in self.monthly_usage[month]:
                self.monthly_usage[month][provider] = TokenUsage()
            self.monthly_usage[month][provider].add(usage)

            # Session usage
            if provider not in self.session_usage:
                self.session_usage[provider] = TokenUsage()
            self.session_usage[provider].add(usage)

            # Update total cost
            self.total_cost += cost_breakdown.total_cost

            # Check budget limits
            self._check_budget_limits()

            # Save updated data
            self.save_usage_data()

            return cost_breakdown

    def _check_budget_limits(self):
        """Check if budget limits have been exceeded."""
        if self.budget_limits.session_limit:
            if self.total_cost >= self.budget_limits.session_limit:
                logger.warning(f"Session budget limit exceeded: ${self.total_cost:.4f}")
                raise RuntimeError(f"Session budget limit exceeded: ${self.total_cost:.4f}")

        today = datetime.now().strftime("%Y-%m-%d")
        if self.budget_limits.daily_limit:
            # Convert tokens to approximate cost for comparison
            daily_cost = sum(
                sum(
                    self.calculate_cost(ModelInfo(), provider_usage).total_cost
                    for provider_usage in day_usage.values()
                )
                for date, day_usage in self.daily_usage.items()
                if date == today
            )

            if daily_cost >= self.budget_limits.daily_limit:
                logger.warning(f"Daily budget limit exceeded: ${daily_cost:.4f}")
                raise RuntimeError(f"Daily budget limit exceeded: ${daily_cost:.4f}")

    def get_daily_usage(self, date: str | None = None) -> dict[str, TokenUsage]:
        """Get daily usage for a specific date."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.daily_usage.get(date, {})

    def get_monthly_usage(self, month: str | None = None) -> dict[str, TokenUsage]:
        """Get monthly usage for a specific month."""
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        return self.monthly_usage.get(month, {})

    def get_session_usage(self) -> dict[str, TokenUsage]:
        """Get usage for current session."""
        return self.session_usage.copy()

    def get_total_cost(self) -> float:
        """Get total accumulated cost."""
        return self.total_cost

    def reset_session(self):
        """Reset session usage."""
        with self.lock:
            self.session_usage.clear()
            self.total_cost = 0.0

    def save_usage_data(self):
        """Save usage data to file."""
        data = {
            "daily_usage": {
                date: {
                    provider: {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cache_write_tokens": usage.cache_write_tokens,
                        "cache_read_tokens": usage.cache_read_tokens,
                        "thoughts_token_count": usage.thoughts_token_count,
                    }
                    for provider, usage in day_usage.items()
                }
                for date, day_usage in self.daily_usage.items()
            },
            "monthly_usage": {
                month: {
                    provider: {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cache_write_tokens": usage.cache_write_tokens,
                        "cache_read_tokens": usage.cache_read_tokens,
                        "thoughts_token_count": usage.thoughts_token_count,
                    }
                    for provider, usage in month_usage.items()
                }
                for month, month_usage in self.monthly_usage.items()
            },
            "total_cost": self.total_cost,
        }

        os.makedirs(os.path.expanduser("~/.hordeforge"), exist_ok=True)
        usage_file = os.path.expanduser("~/.hordeforge/token_usage.json")
        with open(usage_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_usage_data(self):
        """Load usage data from file."""
        usage_file = os.path.expanduser("~/.hordeforge/token_usage.json")
        if os.path.exists(usage_file):
            try:
                with open(usage_file) as f:
                    data = json.load(f)

                # Restore daily usage
                for date, day_data in data.get("daily_usage", {}).items():
                    self.daily_usage[date] = {}
                    for provider, usage_data in day_data.items():
                        # Convert old field names to new field names for backward compatibility
                        converted_data = {}
                        for key, value in usage_data.items():
                            if key == "input_tokens":
                                converted_data["inputTokens"] = value
                            elif key == "output_tokens":
                                converted_data["outputTokens"] = value
                            elif key == "cache_write_tokens":
                                converted_data["cacheWriteTokens"] = value
                            elif key == "cache_read_tokens":
                                converted_data["cacheReadTokens"] = value
                            elif key == "thoughts_token_count":
                                converted_data["thoughtsTokenCount"] = value
                            else:
                                converted_data[key] = value
                        self.daily_usage[date][provider] = TokenUsage(**converted_data)

                # Restore monthly usage
                for month, month_data in data.get("monthly_usage", {}).items():
                    self.monthly_usage[month] = {}
                    for provider, usage_data in month_data.items():
                        # Convert old field names to new field names for backward compatibility
                        converted_data = {}
                        for key, value in usage_data.items():
                            if key == "input_tokens":
                                converted_data["inputTokens"] = value
                            elif key == "output_tokens":
                                converted_data["outputTokens"] = value
                            elif key == "cache_write_tokens":
                                converted_data["cacheWriteTokens"] = value
                            elif key == "cache_read_tokens":
                                converted_data["cacheReadTokens"] = value
                            elif key == "thoughts_token_count":
                                converted_data["thoughtsTokenCount"] = value
                            else:
                                converted_data[key] = value
                        self.monthly_usage[month][provider] = TokenUsage(**converted_data)

                self.total_cost = data.get("total_cost", 0.0)

            except Exception as e:
                logger.error(f"Error loading usage data: {e}")

    def get_usage_summary(self) -> dict:
        """Get comprehensive usage summary."""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")

        return {
            "today": {
                provider: {
                    "total_tokens": usage.total_tokens(),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_tokens": usage.cache_write_tokens + usage.cache_read_tokens,
                    "thoughts_tokens": usage.thoughts_token_count,
                }
                for provider, usage in self.get_daily_usage(today).items()
            },
            "this_month": {
                provider: {
                    "total_tokens": usage.total_tokens(),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_tokens": usage.cache_write_tokens + usage.cache_read_tokens,
                    "thoughts_tokens": usage.thoughts_token_count,
                }
                for provider, usage in self.get_monthly_usage(current_month).items()
            },
            "session": {
                provider: {
                    "total_tokens": usage.total_tokens(),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_tokens": usage.cache_write_tokens + usage.cache_read_tokens,
                    "thoughts_tokens": usage.thoughts_token_count,
                }
                for provider, usage in self.session_usage.items()
            },
            "total_cost": self.total_cost,
            "budget_limits": {
                "daily": self.budget_limits.daily_limit,
                "monthly": self.budget_limits.monthly_limit,
                "session": self.budget_limits.session_limit,
            },
        }


class CostTracker:
    """Simple cost tracker for individual API calls."""

    def __init__(self, budget_system: TokenBudgetSystem):
        self.budget_system = budget_system
        self.pending_usage: list[tuple[str, ModelInfo, TokenUsage]] = []
        self.lock = threading.Lock()

    def record_usage(self, provider: str, model_info: ModelInfo, usage: TokenUsage):
        """Record token usage for later processing."""
        with self.lock:
            self.pending_usage.append((provider, model_info, usage))

    def process_pending_usage(self) -> list[CostBreakdown]:
        """Process all pending usage records."""
        with self.lock:
            results = []
            for provider, model_info, usage in self.pending_usage:
                cost_breakdown = self.budget_system.track_usage(provider, model_info, usage)
                results.append(cost_breakdown)
            self.pending_usage.clear()
            return results

    def get_current_cost(self) -> float:
        """Get current total cost from budget system."""
        return self.budget_system.get_total_cost()


# Global budget system instance
_global_budget_system = None
_global_cost_tracker = None


def get_budget_system() -> TokenBudgetSystem:
    """Get global budget system instance."""
    global _global_budget_system
    if _global_budget_system is None:
        _global_budget_system = TokenBudgetSystem()
    return _global_budget_system


def get_cost_tracker() -> CostTracker:
    """Get global cost tracker instance."""
    global _global_cost_tracker
    if _global_cost_tracker is None:
        _global_cost_tracker = CostTracker(get_budget_system())
    return _global_cost_tracker


def set_budget_limits(limits: BudgetLimits):
    """Set budget limits globally."""
    budget_system = get_budget_system()
    budget_system.budget_limits = limits


def get_usage_summary() -> dict:
    """Get global usage summary."""
    return get_budget_system().get_usage_summary()


def reset_session():
    """Reset global session."""
    get_budget_system().reset_session()


# Backward compatibility utilities for token budget system
def migrate_old_token_format(old_tokens: dict[str, int]) -> dict[str, int]:
    """Migrate old token format to new format for backward compatibility."""
    from .llm_wrapper_backward_compatibility import CompatibilityMigration

    migration = CompatibilityMigration()
    return migration.migrate_old_token_format(old_tokens)


def create_legacy_token_usage(**kwargs) -> TokenUsage:
    """Create legacy token usage object for backward compatibility."""
    # Support both old and new naming conventions
    converted_kwargs = {}
    field_mapping = {
        "input_tokens": "inputTokens",
        "output_tokens": "outputTokens",
        "cache_write_tokens": "cacheWriteTokens",
        "cache_read_tokens": "cacheReadTokens",
        "thoughts_token_count": "thoughtsTokenCount",
    }

    for old_key, new_key in field_mapping.items():
        if old_key in kwargs:
            converted_kwargs[new_key] = kwargs[old_key]
        elif new_key in kwargs:
            converted_kwargs[new_key] = kwargs[new_key]

    return TokenUsage(**converted_kwargs)


def create_legacy_cost_breakdown(**kwargs) -> CostBreakdown:
    """Create legacy cost breakdown object for backward compatibility."""
    # Support both old and new naming conventions
    converted_kwargs = {}
    field_mapping = {
        "input_cost": "inputCost",
        "output_cost": "outputCost",
        "cache_write_cost": "cacheWriteCost",
        "cache_read_cost": "cacheReadCost",
        "thoughts_cost": "thoughtsCost",
        "total_cost": "totalCost",
    }

    for old_key, new_key in field_mapping.items():
        if old_key in kwargs:
            converted_kwargs[new_key] = kwargs[old_key]
        elif new_key in kwargs:
            converted_kwargs[new_key] = kwargs[new_key]

    return CostBreakdown(**converted_kwargs)


def create_legacy_budget_limits(**kwargs) -> BudgetLimits:
    """Create legacy budget limits object for backward compatibility."""
    # Support both old and new naming conventions
    converted_kwargs = {}
    field_mapping = {
        "daily_limit": "dailyLimit",
        "monthly_limit": "monthlyLimit",
        "session_limit": "sessionLimit",
        "reasoning_budget_tokens": "reasoningBudgetTokens",
    }

    for old_key, new_key in field_mapping.items():
        if old_key in kwargs:
            converted_kwargs[new_key] = kwargs[old_key]
        elif new_key in kwargs:
            converted_kwargs[new_key] = kwargs[new_key]

    return BudgetLimits(**converted_kwargs)
