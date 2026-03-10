"""Session management with Redis (HF-P7-002)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import redis

from scheduler.auth.jwt_validator import JWTValidator

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """Session data."""

    session_id: str
    user_id: str
    email: str
    roles: list[str]
    created_at: int
    expires_at: int
    provider: str | None = None


class SessionManager:
    """Session manager using Redis."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_url: str = "redis://localhost:6379",
        session_ttl: int = 3600,
        jwt_secret: str | None = None,
        jwt_algorithm: str = "HS256",
    ) -> None:
        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                self._redis = redis.from_url(redis_url)
            except Exception as e:
                logger.warning("Failed to connect to Redis: %s", e)
                self._redis = None

        self.session_ttl = session_ttl
        self.jwt_secret = jwt_secret or "dev-secret-change-in-production"
        self.jwt_algorithm = jwt_algorithm
        self.jwt_validator = JWTValidator(
            secret_key=self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )

    def _get_session_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"session:{session_id}"

    def create_session(
        self,
        user_id: str,
        email: str,
        roles: list[str] | None = None,
        provider: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> str:
        """Create a new session.

        Args:
            user_id: User identifier
            email: User email
            roles: User roles
            provider: OAuth provider
            extra_data: Additional session data

        Returns:
            Session ID
        """
        import time

        now = int(time.time())
        session_id = str(uuid.uuid4())
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "email": email,
            "roles": roles or ["user"],
            "provider": provider,
            "created_at": now,
            "expires_at": now + self.session_ttl,
        }

        if extra_data:
            session_data["extra"] = extra_data

        key = self._get_session_key(session_id)
        if self._redis:
            self._redis.setex(
                key,
                self.session_ttl,
                json.dumps(session_data),
            )
        else:
            logger.warning("Redis not available, session not persisted")

        logger.info("Created session for user %s", user_id)
        return session_id

    def get_session(self, session_id: str) -> SessionData | None:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found and valid, None otherwise
        """
        key = self._get_session_key(session_id)

        if self._redis:
            data = self._redis.get(key)
            if data is None:
                return None

            session_dict = json.loads(data)
            return SessionData(**session_dict)

        return None

    def validate_session(self, session_id: str) -> SessionData | None:
        """Validate session and return data if valid.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if valid, None otherwise
        """
        session = self.get_session(session_id)

        if session is None:
            return None

        # Check expiration
        import time

        if session.expires_at < int(time.time()):
            # Expired - clean up
            self.delete_session(session_id)
            return None

        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False otherwise
        """
        key = self._get_session_key(session_id)

        if self._redis:
            result = self._redis.delete(key)
            logger.info("Deleted session %s", session_id)
            return result > 0

        return False

    def extend_session(self, session_id: str, ttl: int | None = None) -> bool:
        """Extend session TTL.

        Args:
            session_id: Session identifier
            ttl: New TTL in seconds (default: use session_ttl)

        Returns:
            True if extended, False otherwise
        """
        key = self._get_session_key(session_id)
        ttl = ttl or self.session_ttl

        if self._redis:
            return self._redis.expire(key, ttl)

        return False

    def create_jwt_from_session(self, session_id: str) -> str | None:
        """Create JWT token from session.

        Args:
            session_id: Session identifier

        Returns:
            JWT token or None if session invalid
        """
        session = self.validate_session(session_id)
        if session is None:
            return None

        return self.jwt_validator.create_token(
            subject=session.user_id,
            email=session.email,
            roles=session.roles,
            extra_claims={"session_id": session.session_id},
        )

    def list_user_sessions(self, user_id: str) -> list[SessionData]:
        """List all active sessions for a user.

        Note: This requires Redis KEYS which may not scale well.
        Consider using a user->sessions index for production.

        Args:
            user_id: User identifier

        Returns:
            List of active sessions
        """
        if not self._redis:
            return []

        sessions = []
        # Note: KEYS is O(N) - not recommended for production with many sessions
        for key in self._redis.keys("session:*"):
            data = self._redis.get(key)
            if data:
                session_dict = json.loads(data)
                if session_dict.get("user_id") == user_id:
                    session = SessionData(**session_dict)
                    if self.validate_session(session.session_id):
                        sessions.append(session)

        return sessions


# Module-level convenience functions

_default_session_manager: SessionManager | None = None


def get_session_manager(
    redis_url: str = "redis://localhost:6379",
    session_ttl: int = 3600,
    jwt_secret: str | None = None,
) -> SessionManager:
    """Get default session manager instance.

    Args:
        redis_url: Redis connection URL
        session_ttl: Session TTL in seconds
        jwt_secret: JWT secret key

    Returns:
        SessionManager instance
    """
    global _default_session_manager

    if _default_session_manager is None:
        _default_session_manager = SessionManager(
            redis_url=redis_url,
            session_ttl=session_ttl,
            jwt_secret=jwt_secret,
        )

    return _default_session_manager


def create_session(
    user_id: str,
    email: str,
    roles: list[str] | None = None,
    provider: str | None = None,
) -> str:
    """Convenience function to create a session.

    Args:
        user_id: User identifier
        email: User email
        roles: User roles
        provider: OAuth provider

    Returns:
        Session ID
    """
    manager = get_session_manager()
    return manager.create_session(user_id, email, roles, provider)


def validate_session(session_id: str) -> SessionData | None:
    """Convenience function to validate a session.

    Args:
        session_id: Session identifier

    Returns:
        SessionData if valid, None otherwise
    """
    manager = get_session_manager()
    return manager.validate_session(session_id)


def delete_session(session_id: str) -> bool:
    """Convenience function to delete a session.

    Args:
        session_id: Session identifier

    Returns:
        True if deleted, False otherwise
    """
    manager = get_session_manager()
    return manager.delete_session(session_id)


def get_session(session_id: str) -> SessionData | None:
    """Convenience function to get a session.

    Args:
        session_id: Session identifier

    Returns:
        SessionData if found, None otherwise
    """
    manager = get_session_manager()
    return manager.get_session(session_id)
