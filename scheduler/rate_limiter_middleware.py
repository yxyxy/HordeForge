"""Rate limiting middleware for FastAPI (HF-P7-001-ST02)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from scheduler.rate_limiter import (
    CheckResult,
    RateLimitBackend,
    get_default_api_limiter,
)

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting.

    Applies rate limiting to all requests and returns 429 when limit is exceeded.
    """

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: RateLimitBackend | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter or get_default_api_limiter()
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ready",
            "/metrics",
        ]

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request.

        Uses X-Forwarded-For header if available, otherwise falls back to client host.
        """
        # Check for forwarded header (from proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to client host
        if request.client:
            return request.client.host

        return "unknown"

    def _should_rate_limit(self, request: Request) -> bool:
        """Check if request should be rate limited."""
        path = request.url.path

        # Exclude health/readiness/metrics endpoints
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return False

        return True

    def _build_response(
        self,
        result: CheckResult,
        request: Request,
    ) -> JSONResponse:
        """Build rate limit response with headers."""
        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.retry_after or 0)),
        }

        if result.retry_after is not None:
            headers["Retry-After"] = str(result.retry_after)

        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": result.retry_after,
            },
            headers=headers,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """Process request through rate limiting."""
        # Skip rate limiting for excluded paths
        if not self._should_rate_limit(request):
            return await call_next(request)

        # Get client identifier
        client_id = self._get_client_id(request)
        endpoint = request.url.path

        # Check rate limit
        result = self.rate_limiter.check_rate_limit(client_id, endpoint)

        # Add rate limit headers to successful responses too
        if result.allowed:
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            return response

        # Rate limit exceeded
        logger.warning(
            "rate_limit_exceeded client=%s endpoint=%s path=%s",
            client_id,
            endpoint,
            request.url.path,
        )
        return self._build_response(result, request)


def create_rate_limited_app(
    app: ASGIApp,
    rate_limiter: RateLimitBackend | None = None,
    exclude_paths: list[str] | None = None,
) -> ASGIApp:
    """Create rate-limited FastAPI application.

    Args:
        app: Original FastAPI application
        rate_limiter: Rate limiter instance
        exclude_paths: Paths to exclude from rate limiting

    Returns:
        Application with rate limiting middleware
    """
    middleware = RateLimitMiddleware(
        app,
        rate_limiter=rate_limiter,
        exclude_paths=exclude_paths,
    )
    return middleware
