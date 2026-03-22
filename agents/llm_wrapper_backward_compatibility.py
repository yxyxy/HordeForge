"""Backward Compatibility Layer for LLM Wrapper - Cline Compatible"""

from __future__ import annotations

import logging
import time
from typing import Any

# Explicit imports instead of star imports for clarity and to avoid Ruff warnings
from .llm_api import (
    ApiStream,
    ApiStreamChunk,
    ApiStreamTextChunk,
    ApiStreamThinkingChunk,
    ApiStreamToolCallsChunk,
    ApiStreamUsageChunk,
    LLMResponse,
    LLMRouter,
    LLMWrapper,
    ModelInfo,
    build_code_prompt,
    build_code_review_prompt,
    build_spec_prompt,
    detect_language,
    detect_spec_type,
    generate_code_with_retry,
    generate_spec_with_retry,
    get_llm_wrapper,
    parse_code_output,
    parse_review_output,
    parse_spec_output,
)

# Rest of the file remains the same

logger = logging.getLogger(__name__)


class LegacyLLMWrapper:
    """Legacy LLM wrapper maintaining backward compatibility with existing API calls."""

    def __init__(self, provider: str = "openai", **kwargs):
        """Initialize legacy wrapper with backward compatibility."""
        self.provider = provider
        self.kwargs = kwargs

        # Map legacy provider names to new ones
        provider_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "google",
            "gemini": "google",
            "claude": "anthropic",
        }

        mapped_provider = provider_map.get(provider.lower(), provider.lower())
        self._wrapper = get_llm_wrapper(provider=mapped_provider, **kwargs)

        if self._wrapper is None:
            # Fallback to OpenAI if provider not found
            self._wrapper = get_llm_wrapper(provider="openai", **kwargs)

    def complete(self, prompt: str, **kwargs) -> str:
        """Legacy complete method - maintains backward compatibility."""
        if hasattr(self._wrapper, "complete"):
            return self._wrapper.complete(prompt, **kwargs)
        else:
            # Fallback implementation
            raise NotImplementedError(f"Complete method not available for {self.provider}")

    def complete_stream(self, prompt: str, **kwargs) -> Any:
        """Legacy streaming method - maintains backward compatibility."""
        if hasattr(self._wrapper, "complete_stream"):
            return self._wrapper.complete_stream(prompt, **kwargs)
        else:
            # Fallback implementation
            raise NotImplementedError(f"Complete stream method not available for {self.provider}")

    def close(self):
        """Close wrapper connections."""
        if hasattr(self._wrapper, "close"):
            self._wrapper.close()


class LegacyModelInfo:
    """Legacy ModelInfo class for backward compatibility."""

    def __init__(self, **kwargs):
        # Support both old and new naming conventions
        self.name = kwargs.get("name", kwargs.get("model_name", None))
        self.max_tokens = kwargs.get("max_tokens", kwargs.get("maxTokens", 4096))
        self.context_window = kwargs.get("context_window", kwargs.get("contextWindow", 128000))
        self.supports_images = kwargs.get("supports_images", kwargs.get("supportsImages", False))
        self.supports_prompt_cache = kwargs.get(
            "supports_prompt_cache", kwargs.get("supportsPromptCache", False)
        )
        self.supports_reasoning = kwargs.get(
            "supports_reasoning", kwargs.get("supportsReasoning", False)
        )
        self.input_price = kwargs.get("input_price", kwargs.get("inputPrice", 0.0))
        self.output_price = kwargs.get("output_price", kwargs.get("outputPrice", 0.0))
        self.cache_writes_price = kwargs.get(
            "cache_writes_price", kwargs.get("cacheWritesPrice", 0.0)
        )
        self.cache_reads_price = kwargs.get("cache_reads_price", kwargs.get("cacheReadsPrice", 0.0))
        self.temperature = kwargs.get("temperature", kwargs.get("temperature", 0.7))
        self.supports_global_endpoint = kwargs.get(
            "supports_global_endpoint", kwargs.get("supportsGlobalEndpoint", False)
        )
        self.thinking_config = kwargs.get("thinking_config", kwargs.get("thinkingConfig", None))
        self.tiers = kwargs.get("tiers", kwargs.get("tiers", None))

        # Cline-compatible properties
        self.maxTokens = self.max_tokens
        self.contextWindow = self.context_window
        self.supportsImages = self.supports_images
        self.supportsPromptCache = self.supports_prompt_cache
        self.supportsReasoning = self.supports_reasoning
        self.inputPrice = self.input_price
        self.outputPrice = self.output_price
        self.cacheWritesPrice = self.cache_writes_price
        self.cacheReadsPrice = self.cache_reads_price
        self.supportsGlobalEndpoint = self.supports_global_endpoint
        self.thinkingConfig = self.thinking_config


class LegacyTokenBudget:
    """Legacy TokenBudget class for backward compatibility."""

    def __init__(self, **kwargs):
        self.prompt_tokens = kwargs.get("prompt_tokens", 0)
        self.completion_tokens = kwargs.get("completion_tokens", 0)
        self.total_tokens = kwargs.get("total_tokens", 0)
        self.max_tokens = kwargs.get("max_tokens", 4000)

        # Cline-compatible properties
        self.promptTokens = self.prompt_tokens
        self.completionTokens = self.completion_tokens
        self.totalTokens = self.total_tokens
        self.maxTokens = self.max_tokens

    @property
    def context_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.context_tokens

    def is_within_budget(self, estimated_completion: int = 500) -> bool:
        return self.context_tokens + estimated_completion <= self.max_tokens


def get_legacy_llm_wrapper(provider: str = "openai", **kwargs) -> LegacyLLMWrapper:
    """Factory function for legacy LLM wrapper - maintains backward compatibility."""
    return LegacyLLMWrapper(provider=provider, **kwargs)


def create_legacy_model_info(**kwargs) -> LegacyModelInfo:
    """Create legacy model info with backward compatibility."""
    return LegacyModelInfo(**kwargs)


def create_legacy_token_budget(**kwargs) -> LegacyTokenBudget:
    """Create legacy token budget with backward compatibility."""
    return LegacyTokenBudget(**kwargs)


# Migration utilities
class CompatibilityMigration:
    """Utilities for migrating from old to new LLM wrapper system."""

    @staticmethod
    def migrate_old_config(old_config: dict[str, Any]) -> dict[str, Any]:
        """Migrate old configuration format to new format."""
        new_config = {}

        # Map old keys to new keys
        key_mapping = {
            "model_name": "model",
            "api_key": "api_key",
            "timeout": "timeout",
            "max_retries": "max_retries",
            "temperature": "temperature",
            "max_tokens": "max_tokens",
        }

        for old_key, new_key in key_mapping.items():
            if old_key in old_config:
                new_config[new_key] = old_config[old_key]

        # Handle provider mapping
        if "provider" in old_config:
            provider_map = {
                "openai": "openai",
                "anthropic": "anthropic",
                "google": "google",
                "gemini": "google",
                "claude": "anthropic",
                "gpt": "openai",
                "claude_model": "anthropic",
            }
            old_provider = old_config["provider"]
            new_config["provider"] = provider_map.get(old_provider.lower(), old_provider.lower())

        return new_config

    @staticmethod
    def migrate_old_token_format(old_tokens: dict[str, int]) -> dict[str, int]:
        """Migrate old token format to new format."""
        new_tokens = {}

        # Support both old and new naming conventions
        field_mapping = {
            "input_tokens": ["input_tokens", "prompt_tokens", "promptTokens"],
            "output_tokens": ["output_tokens", "completionTokens"],
            "total_tokens": ["total_tokens", "totalTokens"],
            "max_tokens": ["max_tokens", "maxTokens"],
        }

        for new_field, old_fields in field_mapping.items():
            for old_field in old_fields:
                if old_field in old_tokens:
                    new_tokens[new_field] = old_tokens[old_field]
                    break

        return new_tokens


# Backward compatibility aliases
LegacyLLMResponse = LLMResponse
LegacyApiStreamChunk = ApiStreamChunk
LegacyApiStreamTextChunk = ApiStreamTextChunk
LegacyApiStreamUsageChunk = ApiStreamUsageChunk
LegacyApiStreamToolCallsChunk = ApiStreamToolCallsChunk
LegacyApiStreamThinkingChunk = ApiStreamThinkingChunk
LegacyApiStream = ApiStream

# Function aliases for backward compatibility
legacy_build_spec_prompt = build_spec_prompt
legacy_parse_spec_output = parse_spec_output
legacy_generate_spec_with_retry = generate_spec_with_retry
legacy_build_code_prompt = build_code_prompt
legacy_parse_code_output = parse_code_output
legacy_generate_code_with_retry = generate_code_with_retry
legacy_detect_spec_type = detect_spec_type
legacy_detect_language = detect_language


# Additional legacy functions that may be needed
def legacy_build_code_review_prompt(
    files: list[dict[str, Any]], spec: dict[str, Any] = None
) -> str:
    """Legacy function for building code review prompts."""
    return build_code_review_prompt(files, spec)


def legacy_parse_review_output(output: str) -> dict[str, Any]:
    """Legacy function for parsing review output."""
    return parse_review_output(output)


def legacy_generate_review_with_retry(
    llm: LLMWrapper,
    files: list[dict[str, Any]],
    spec: dict[str, Any] = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Legacy function for generating review with retry logic."""
    last_error = None

    for attempt in range(max_retries):
        try:
            prompt = legacy_build_code_review_prompt(files, spec)
            response = llm.complete(prompt)
            result = legacy_parse_review_output(response)
            logger.info(f"Review generated successfully on attempt {attempt + 1}")
            return result
        except ValueError as e:
            last_error = e
            logger.warning(f"Review generation attempt {attempt + 1} failed: {e}")

            if attempt < max_retries - 1:
                context_dict = {}
                context_dict["_retry_hint"] = (
                    f"Previous attempt failed: {e}. Ensure valid JSON output."
                )

    raise ValueError(f"Review generation failed after {max_retries} attempts: {last_error}")


# Router compatibility
class LegacyLLMRouter:
    """Legacy LLM Router maintaining backward compatibility."""

    def __init__(self, **kwargs):
        self._router = LLMRouter(**kwargs)

    def for_task(self, task: str) -> LLMWrapper:
        """Get LLM wrapper for specific task."""
        return self._router.for_task(task)

    def for_model(self, provider: str, model: str) -> LLMWrapper:
        """Get LLM wrapper for specific provider and model."""
        return self._router.for_model(provider, model)

    def set_custom_route(self, task: str, provider: str, model: str, description: str = ""):
        """Set custom routing for a task."""
        self._router.set_custom_route(task, provider, model, description)

    def get_routing_info(self) -> dict:
        """Get current routing configuration."""
        return self._router.get_routing_info()

    def close_all(self):
        """Close all cached wrappers."""
        self._router.close_all()


def get_legacy_router(**kwargs) -> LegacyLLMRouter:
    """Get legacy router instance."""
    return LegacyLLMRouter(**kwargs)


# Configuration migration helper
def migrate_configuration(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate configuration from old format to new format with backward compatibility."""
    migration = CompatibilityMigration()
    return migration.migrate_old_config(config)


# Utility functions for backward compatibility
def legacy_get_model_info(provider: str, model: str) -> ModelInfo:
    """Get model info with backward compatibility."""
    wrapper = get_llm_wrapper(provider=provider, model=model)
    if wrapper and hasattr(wrapper, "get_model"):
        return wrapper.get_model()[1]  # Return ModelInfo object
    return ModelInfo(name=model)


def legacy_calculate_tokens(text: str) -> int:
    """Calculate tokens with backward compatibility."""
    # Simple approximation - in real implementation would use proper tokenizer
    return len(text.split()) * 1.3  # Rough approximation


# Flag-based gradual migration system
class MigrationFlags:
    """System for gradual migration with feature flags."""

    def __init__(self):
        self.flags = {
            "use_new_wrapper": False,  # Default to old behavior
            "strict_compatibility": True,
            "allow_deprecated": True,
            "log_compatibility_warnings": True,
        }

    def set_flag(self, flag_name: str, value: bool):
        """Set a migration flag."""
        self.flags[flag_name] = value

    def get_flag(self, flag_name: str) -> bool:
        """Get a migration flag value."""
        return self.flags.get(flag_name, False)

    def is_using_new_system(self) -> bool:
        """Check if new system should be used."""
        return self.flags.get("use_new_wrapper", False)


# Global migration flag instance
_migration_flags = MigrationFlags()


def set_migration_flag(flag_name: str, value: bool):
    """Set a global migration flag."""
    _migration_flags.set_flag(flag_name, value)


def get_migration_flag(flag_name: str) -> bool:
    """Get a global migration flag."""
    return _migration_flags.get_flag(flag_name)


def enable_new_system():
    """Enable the new system for gradual migration."""
    _migration_flags.set_flag("use_new_wrapper", True)
    _migration_flags.set_flag("strict_compatibility", False)


def disable_new_system():
    """Disable the new system and revert to legacy."""
    _migration_flags.set_flag("use_new_wrapper", False)
    _migration_flags.set_flag("strict_compatibility", True)


# Rollback capability
class RollbackManager:
    """Manager for handling rollbacks to legacy system."""

    def __init__(self):
        self.rollback_points = {}
        self.current_state = "legacy"

    def create_rollback_point(self, name: str, state: dict[str, Any]):
        """Create a rollback point."""
        self.rollback_points[name] = {
            "state": state,
            "timestamp": time.time(),
            "system": self.current_state,
        }

    def rollback_to_point(self, name: str) -> bool:
        """Rollback to a specific point."""
        if name in self.rollback_points:
            point = self.rollback_points[name]
            self.current_state = point["system"]
            # Restore state logic would go here
            logger.info(f"Rolled back to {name} - system now {self.current_state}")
            return True
        return False

    def get_current_state(self) -> str:
        """Get current system state."""
        return self.current_state


# Global rollback manager
_rollback_manager = RollbackManager()


def create_migration_rollback_point(name: str, state: dict[str, Any]):
    """Create a migration rollback point."""
    _rollback_manager.create_rollback_point(name, state)


def rollback_from_migration(name: str) -> bool:
    """Rollback from migration to previous state."""
    return _rollback_manager.rollback_to_point(name)


# Alert system for compatibility issues
class CompatibilityAlertSystem:
    """System for alerting about compatibility issues."""

    def __init__(self):
        self.alerts = []
        self.handlers = []

    def add_alert_handler(self, handler):
        """Add an alert handler."""
        self.handlers.append(handler)

    def log_compatibility_issue(self, issue: str, severity: str = "warning"):
        """Log a compatibility issue."""
        alert = {
            "issue": issue,
            "severity": severity,
            "timestamp": time.time(),
            "type": "compatibility",
        }
        self.alerts.append(alert)

        # Trigger handlers
        for handler in self.handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")

    def get_alerts(self) -> list[dict[str, Any]]:
        """Get all alerts."""
        return self.alerts

    def clear_alerts(self):
        """Clear all alerts."""
        self.alerts.clear()


# Global alert system
_compat_alert_system = CompatibilityAlertSystem()


def add_compatibility_alert_handler(handler):
    """Add a compatibility alert handler."""
    _compat_alert_system.add_alert_handler(handler)


def log_compatibility_issue(issue: str, severity: str = "warning"):
    """Log a compatibility issue."""
    _compat_alert_system.log_compatibility_issue(issue, severity)


def get_compatibility_alerts() -> list[dict[str, Any]]:
    """Get all compatibility alerts."""
    return _compat_alert_system.get_alerts()


# Initialize logging for compatibility
def initialize_compatibility_logging():
    """Initialize logging for compatibility tracking."""
    if _migration_flags.get_flag("log_compatibility_warnings"):

        def log_handler(alert):
            logger.warning(f"Compatibility {alert['severity']}: {alert['issue']}")

        _compat_alert_system.add_alert_handler(log_handler)


# Initialize on module load
initialize_compatibility_logging()


__all__ = [
    "LegacyLLMWrapper",
    "LegacyModelInfo",
    "LegacyTokenBudget",
    "get_legacy_llm_wrapper",
    "create_legacy_model_info",
    "create_legacy_token_budget",
    "CompatibilityMigration",
    "LegacyLLMResponse",
    "LegacyApiStreamChunk",
    "LegacyApiStreamTextChunk",
    "LegacyApiStreamUsageChunk",
    "LegacyApiStreamToolCallsChunk",
    "LegacyApiStreamThinkingChunk",
    "LegacyApiStream",
    "legacy_build_spec_prompt",
    "legacy_parse_spec_output",
    "legacy_generate_spec_with_retry",
    "legacy_build_code_prompt",
    "legacy_parse_code_output",
    "legacy_generate_code_with_retry",
    "legacy_detect_spec_type",
    "legacy_detect_language",
    "LegacyLLMRouter",
    "get_legacy_router",
    "migrate_configuration",
    "legacy_get_model_info",
    "legacy_calculate_tokens",
    "MigrationFlags",
    "set_migration_flag",
    "get_migration_flag",
    "enable_new_system",
    "disable_new_system",
    "RollbackManager",
    "create_migration_rollback_point",
    "rollback_from_migration",
    "CompatibilityAlertSystem",
    "add_compatibility_alert_handler",
    "log_compatibility_issue",
    "get_compatibility_alerts",
    "initialize_compatibility_logging",
]
