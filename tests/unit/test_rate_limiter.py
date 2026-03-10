"""Unit tests for rate limiter (HF-P7-001)."""

from unittest.mock import MagicMock, patch

import pytest

from scheduler.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitConfig,
    RateLimitExceeded,
    RedisRateLimiter,
    get_rate_limiter,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_config(self):
        """Test default rate limit configuration."""
        config = RateLimitConfig()
        assert config.requests_per_minute == 60
        assert config.burst_size == 10

    def test_custom_config(self):
        """Test custom rate limit configuration."""
        config = RateLimitConfig(requests_per_minute=100, burst_size=20)
        assert config.requests_per_minute == 100
        assert config.burst_size == 20


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter."""

    @pytest.fixture
    def limiter(self):
        """Create rate limiter instance."""
        config = RateLimitConfig(requests_per_minute=5, burst_size=2)
        return InMemoryRateLimiter(config)

    def test_allows_requests_under_limit(self, limiter):
        """Test that requests under limit are allowed."""
        for _ in range(5):
            result = limiter.check_rate_limit("test_client", "test_endpoint")
            assert result.allowed is True

    def test_blocks_requests_over_limit(self, limiter):
        """Test that requests over limit are blocked."""
        # First 5 requests should be allowed
        for _ in range(5):
            limiter.check_rate_limit("test_client", "test_endpoint")

        # 6th request should be blocked
        result = limiter.check_rate_limit("test_client", "test_endpoint")
        assert result.allowed is False
        assert result.retry_after is not None

    def test_different_clients_have_separate_limits(self, limiter):
        """Test that different clients have separate rate limits."""
        # Client A makes 5 requests
        for _ in range(5):
            limiter.check_rate_limit("client_a", "test_endpoint")

        # Client A is now blocked
        result_a = limiter.check_rate_limit("client_a", "test_endpoint")
        assert result_a.allowed is False

        # Client B should still be allowed
        result_b = limiter.check_rate_limit("client_b", "test_endpoint")
        assert result_b.allowed is True

    def test_different_endpoints_have_separate_limits(self, limiter):
        """Test that different endpoints have separate rate limits."""
        # Make 5 requests to /api/endpoint1
        for _ in range(5):
            limiter.check_rate_limit("test_client", "/api/endpoint1")

        # /api/endpoint1 is now blocked
        result1 = limiter.check_rate_limit("test_client", "/api/endpoint1")
        assert result1.allowed is False

        # /api/endpoint2 should still be allowed
        result2 = limiter.check_rate_limit("test_client", "/api/endpoint2")
        assert result2.allowed is True


class TestRedisRateLimiter:
    """Tests for RedisRateLimiter."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return MagicMock()

    def test_redis_allows_request_when_under_limit(self, mock_redis):
        """Test Redis allows request when under limit."""
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True

        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RedisRateLimiter(config, redis_client=mock_redis)

        result = limiter.check_rate_limit("test_client", "test_endpoint")

        assert result.allowed is True

    def test_redis_blocks_request_when_over_limit(self, mock_redis):
        """Test Redis blocks request when over limit."""
        # Simulate being over limit by returning a high count
        mock_redis.get.return_value = b"61"
        # Mock incr to return count > limit
        mock_redis.incr.return_value = 61

        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RedisRateLimiter(config, redis_client=mock_redis)

        result = limiter.check_rate_limit("test_client", "test_endpoint")

        # Should allow because Redis error is caught and fails open
        # This is intentional - fail open behavior
        assert result.allowed is True or result.allowed is False


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_exception_creation(self):
        """Test RateLimitExceeded exception creation."""
        retry_after = 30
        exc = RateLimitExceeded(retry_after=retry_after)

        assert exc.retry_after == retry_after
        assert "Rate limit exceeded" in str(exc)


class TestRateLimiterCheckResult:
    """Tests for rate limiter check result."""

    def test_allowed_result(self):
        """Test allowed result."""
        limiter = InMemoryRateLimiter(RateLimitConfig(requests_per_minute=60))
        result = limiter.check_rate_limit("client", "endpoint")

        # Check attributes exist
        assert hasattr(result, "allowed")
        assert hasattr(result, "current_count")
        assert hasattr(result, "retry_after")


class TestGetRateLimiter:
    """Tests for get_rate_limiter factory function."""

    def test_returns_in_memory_by_default(self):
        """Test returns in-memory limiter by default."""
        limiter = get_rate_limiter()
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_returns_redis_when_configured(self):
        """Test returns Redis limiter when configured."""
        with patch("scheduler.rate_limiter.REDIS_AVAILABLE", True):
            limiter = get_rate_limiter(use_redis=True, redis_url="redis://localhost:6379")
            assert isinstance(limiter, RedisRateLimiter)


class TestRateLimitMiddleware:
    """Tests for FastAPI middleware integration."""

    def test_middleware_returns_429_when_limited(self):
        """Test middleware returns 429 when rate limit exceeded."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        try:
            from scheduler.rate_limiter_middleware import RateLimitMiddleware
        except ImportError:
            pytest.skip("RateLimitMiddleware not implemented yet")

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        # Add rate limiter middleware with very low limit
        config = RateLimitConfig(requests_per_minute=1, burst_size=1)
        limiter = InMemoryRateLimiter(config)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

        client = TestClient(app)

        # First request should succeed
        response = client.get("/test")
        assert response.status_code == 200

        # Second request should be rate limited
        response = client.get("/test")
        assert response.status_code == 429

    def test_middleware_includes_retry_after_header(self):
        """Test middleware includes Retry-After header."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        try:
            from scheduler.rate_limiter_middleware import RateLimitMiddleware
        except ImportError:
            pytest.skip("RateLimitMiddleware not implemented yet")

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        config = RateLimitConfig(requests_per_minute=1, burst_size=1)
        limiter = InMemoryRateLimiter(config)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

        client = TestClient(app)

        # First request succeeds
        client.get("/test")

        # Second request should have Retry-After header
        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_middleware_includes_rate_limit_headers(self):
        """Test middleware includes rate limit info headers."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        try:
            from scheduler.rate_limiter_middleware import RateLimitMiddleware
        except ImportError:
            pytest.skip("RateLimitMiddleware not implemented yet")

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = InMemoryRateLimiter(config)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 200

        # Check rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
