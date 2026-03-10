"""Rate limiting for HordeForge API (HF-P7-001).

This module provides rate limiting functionality to protect the API
from abuse and DDoS attacks.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Redis availability flag
REDIS_AVAILABLE = True

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    burst_size: int = 10


@dataclass
class CheckResult:
    """Result of rate limit check."""

    allowed: bool
    current_count: int
    retry_after: int | None = None
    limit: int = 60
    remaining: int = 60


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, retry_after: int, message: str = "Rate limit exceeded"):
        self.retry_after = retry_after
        super().__init__(message)


class RateLimitBackend(ABC):
    """Abstract base class for rate limiter backends."""

    @abstractmethod
    def check_rate_limit(
        self,
        client_id: str,
        endpoint: str,
    ) -> CheckResult:
        """Check if request is allowed.

        Args:
            client_id: Unique identifier for the client
            endpoint: API endpoint being accessed

        Returns:
            CheckResult with allowed status and metadata
        """
        pass


class InMemoryRateLimiter(RateLimitBackend):
    """In-memory rate limiter implementation.

    Uses a sliding window algorithm for rate limiting.
    Suitable for development and small deployments.
    """

    def __init__(
        self,
        config: RateLimitConfig | None = None,
    ) -> None:
        self.config = config or RateLimitConfig()
        self._counters: dict[str, tuple[int, float]] = {}  # key -> (count, window_start)
        self._window_size = 60.0  # 1 minute window
        self.logger = logging.getLogger("hordeforge.rate_limiter")

    def _get_key(self, client_id: str, endpoint: str) -> str:
        """Generate storage key for client+endpoint."""
        return f"{client_id}:{endpoint}"

    def _cleanup_old_windows(self, key: str) -> None:
        """Remove expired windows."""
        if key in self._counters:
            count, window_start = self._counters[key]
            now = time.time()
            if now - window_start >= self._window_size:
                del self._counters[key]

    def check_rate_limit(
        self,
        client_id: str,
        endpoint: str,
    ) -> CheckResult:
        """Check if request is allowed.

        Args:
            client_id: Unique identifier for the client
            endpoint: API endpoint being accessed

        Returns:
            CheckResult with allowed status and metadata
        """
        key = self._get_key(client_id, endpoint)
        now = time.time()

        # Cleanup old windows
        self._cleanup_old_windows(key)

        # Get current count
        if key in self._counters:
            count, window_start = self._counters[key]
        else:
            count = 0
            window_start = now

        # Check if we can allow this request
        limit = self.config.requests_per_minute

        if count < limit:
            # Allow request
            self._counters[key] = (count + 1, window_start)
            remaining = limit - count - 1
            self.logger.debug(
                "rate_limit_allowed client=%s endpoint=%s count=%d limit=%d remaining=%d",
                client_id,
                endpoint,
                count + 1,
                limit,
                remaining,
            )
            return CheckResult(
                allowed=True,
                current_count=count + 1,
                limit=limit,
                remaining=remaining,
            )
        else:
            # Rate limit exceeded
            retry_after = int(self._window_size - (now - window_start))
            self.logger.warning(
                "rate_limit_exceeded client=%s endpoint=%s count=%d limit=%d",
                client_id,
                endpoint,
                count,
                limit,
            )
            return CheckResult(
                allowed=False,
                current_count=count,
                retry_after=retry_after,
                limit=limit,
                remaining=0,
            )


class RedisRateLimiter(RateLimitBackend):
    """Redis-based rate limiter implementation.

    Uses Redis for distributed rate limiting.
    Suitable for production deployments.
    """

    def __init__(
        self,
        config: RateLimitConfig | None = None,
        redis_client: Any | None = None,
        redis_url: str = "redis://localhost:6379",
    ) -> None:
        self.config = config or RateLimitConfig()
        self.redis_url = redis_url

        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                import redis

                self._redis = redis.from_url(redis_url)
            except ImportError:
                self._redis = None
                logger.warning("Redis not available, falling back to in-memory")

        self.logger = logging.getLogger("hordeforge.rate_limiter.redis")

    def check_rate_limit(
        self,
        client_id: str,
        endpoint: str,
    ) -> CheckResult:
        """Check if request is allowed using Redis.

        Args:
            client_id: Unique identifier for the client
            endpoint: API endpoint being accessed

        Returns:
            CheckResult with allowed status and metadata
        """
        if self._redis is None:
            # Fallback to in-memory
            fallback = InMemoryRateLimiter(self.config)
            return fallback.check_rate_limit(client_id, endpoint)

        key = f"rate_limit:{client_id}:{endpoint}"
        limit = self.config.requests_per_minute
        window = 60  # 1 minute

        try:
            # Increment counter
            current = self._redis.incr(key)

            # Set expiry on first increment
            if current == 1:
                self._redis.expire(key, window)

            if current <= limit:
                return CheckResult(
                    allowed=True,
                    current_count=current,
                    limit=limit,
                    remaining=limit - current,
                )
            else:
                # Get TTL for retry-after
                ttl = self._redis.ttl(key)
                retry_after = ttl if ttl > 0 else window

                return CheckResult(
                    allowed=False,
                    current_count=current,
                    retry_after=retry_after,
                    limit=limit,
                    remaining=0,
                )
        except Exception as e:
            logger.error("Redis rate limit error: %s", e)
            # Fail open - allow request on Redis errors
            return CheckResult(
                allowed=True,
                current_count=0,
                limit=limit,
                remaining=limit,
            )


def get_rate_limiter(
    use_redis: bool = False,
    redis_url: str = "redis://localhost:6379",
    config: RateLimitConfig | None = None,
) -> RateLimitBackend:
    """Factory function to get rate limiter instance.

    Args:
        use_redis: Whether to use Redis backend
        redis_url: Redis connection URL
        config: Rate limit configuration

    Returns:
        RateLimitBackend implementation
    """
    if use_redis and REDIS_AVAILABLE:
        return RedisRateLimiter(config=config, redis_url=redis_url)
    return InMemoryRateLimiter(config=config)


# Default instances for different use cases
def get_default_api_limiter() -> RateLimitBackend:
    """Get default rate limiter for API endpoints."""
    config = RateLimitConfig(requests_per_minute=60, burst_size=10)
    return get_rate_limiter(config=config)


def get_strict_limiter() -> RateLimitBackend:
    """Get strict rate limiter for sensitive endpoints."""
    config = RateLimitConfig(requests_per_minute=10, burst_size=2)
    return get_rate_limiter(config=config)


# Alias for backward compatibility
RateLimiter = RateLimitBackend  # type: ignore[misc,assignment]
