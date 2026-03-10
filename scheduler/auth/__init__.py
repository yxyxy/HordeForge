"""Authentication module (HF-P7-002).

This module provides OAuth/OIDC authentication, JWT validation, and session management.
"""

from scheduler.auth.jwt_validator import (
    JWTValidator,
    decode_jwt_payload,
    validate_jwt_token,
)
from scheduler.auth.oauth_providers import (
    GitHubOAuthProvider,
    GoogleOAuthProvider,
    OAuthProvider,
    OIDCOAuthProvider,
    get_oauth_provider,
)
from scheduler.auth.session_manager import (
    SessionManager,
    create_session,
    delete_session,
    get_session,
    validate_session,
)

__all__ = [
    "OAuthProvider",
    "GoogleOAuthProvider",
    "GitHubOAuthProvider",
    "OIDCOAuthProvider",
    "get_oauth_provider",
    "JWTValidator",
    "validate_jwt_token",
    "decode_jwt_payload",
    "SessionManager",
    "create_session",
    "validate_session",
    "delete_session",
    "get_session",
]
