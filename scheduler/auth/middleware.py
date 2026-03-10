"""Authentication middleware for FastAPI (HF-P7-002)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from scheduler.auth.jwt_validator import JWTValidator
from scheduler.auth.session_manager import SessionManager

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for authentication.

    Validates JWT tokens or session cookies for protected endpoints.
    """

    def __init__(
        self,
        app: ASGIApp,
        session_manager: SessionManager | None = None,
        jwt_validator: JWTValidator | None = None,
        public_paths: list[str] | None = None,
        login_url: str = "/auth/login",
    ) -> None:
        super().__init__(app)
        self.session_manager = session_manager
        self.jwt_validator = jwt_validator
        self.public_paths = public_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/auth/login",
            "/auth/callback",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]
        self.login_url = login_url

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require auth)."""
        for public in self.public_paths:
            if path.startswith(public):
                return True
        return False

    def _extract_token(self, request: Request) -> str | None:
        """Extract authentication token from request."""
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Check session cookie
        session_cookie = request.cookies.get("session_id")
        if session_cookie:
            return f"session:{session_cookie}"

        return None

    def _extract_session_id(self, request: Request) -> str | None:
        """Extract session ID from cookie."""
        return request.cookies.get("session_id")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """Process request through authentication."""
        # Skip auth for public paths
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)

        if not token:
            # No token - redirect to login or return 401
            if request.url.path.startswith("/api"):
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "message": "Authentication required"},
                )
            return RedirectResponse(url=self.login_url)

        # Validate token
        user_info = None

        if token.startswith("session:"):
            # Session-based auth
            session_id = token[8:]
            if self.session_manager:
                session = self.session_manager.validate_session(session_id)
                if session:
                    user_info = {
                        "user_id": session.user_id,
                        "email": session.email,
                        "roles": session.roles,
                        "session_id": session.session_id,
                    }
        else:
            # JWT-based auth
            if self.jwt_validator:
                payload = self.jwt_validator.validate_token(token)
                if payload:
                    user_info = {
                        "user_id": payload.subject,
                        "email": payload.email,
                        "roles": payload.roles or [],
                    }

        if user_info is None:
            # Invalid token - return 401
            if request.url.path.startswith("/api"):
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "message": "Invalid or expired token"},
                )
            return RedirectResponse(url=self.login_url)

        # Attach user info to request state
        request.state.user = user_info

        # Process request
        response = await call_next(request)

        # Add user info headers to response
        response.headers["X-User-ID"] = user_info.get("user_id", "")
        if user_info.get("email"):
            response.headers["X-User-Email"] = user_info["email"]

        return response


def create_authenticated_app(
    app: ASGIApp,
    session_manager: SessionManager | None = None,
    jwt_validator: JWTValidator | None = None,
    public_paths: list[str] | None = None,
    login_url: str = "/auth/login",
) -> ASGIApp:
    """Create authenticated FastAPI application.

    Args:
        app: Original FastAPI application
        session_manager: Session manager instance
        jwt_validator: JWT validator instance
        public_paths: Paths that don't require authentication
        login_url: Login page URL for redirects

    Returns:
        Application with authentication middleware
    """
    middleware = AuthMiddleware(
        app,
        session_manager=session_manager,
        jwt_validator=jwt_validator,
        public_paths=public_paths,
        login_url=login_url,
    )
    return middleware
