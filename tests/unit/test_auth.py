"""Unit tests for OAuth/OIDC authentication (HF-P7-002)."""

from unittest.mock import MagicMock, patch

import pytest

from scheduler.auth.jwt_validator import (
    JWTValidator,
    decode_jwt_payload,
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
)


class TestOAuthProvider:
    """Tests for OAuth provider abstraction."""

    def test_oauth_provider_abstract_methods(self):
        """Test that OAuthProvider is abstract."""
        with pytest.raises(TypeError):
            OAuthProvider()

    def test_google_oauth_get_authorization_url(self):
        """Test Google OAuth authorization URL generation."""
        provider = GoogleOAuthProvider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        url = provider.get_authorization_url("test_state")

        assert "accounts.google.com" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "state=test_state" in url

    def test_github_oauth_get_authorization_url(self):
        """Test GitHub OAuth authorization URL generation."""
        provider = GitHubOAuthProvider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        url = provider.get_authorization_url("test_state")

        assert "github.com" in url
        assert "client_id=test_client_id" in url
        assert "state=test_state" in url

    def test_oidc_oauth_get_authorization_url(self):
        """Test generic OIDC OAuth authorization URL generation."""
        provider = OIDCOAuthProvider(
            issuer_url="https://identity.example.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        url = provider.get_authorization_url("test_state")

        assert "identity.example.com" in url
        assert "client_id=test_client_id" in url


class TestGoogleOAuthProvider:
    """Tests for Google OAuth provider."""

    def test_exchange_code_for_token(self):
        """Test token exchange."""

        provider = GoogleOAuthProvider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "id_token": "test_id_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = provider.exchange_code_for_token("test_code")

            assert result["access_token"] == "test_access_token"
            assert result["id_token"] == "test_id_token"

    def test_get_user_info(self):
        """Test getting user info."""

        provider = GoogleOAuthProvider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "sub": "user123",
                "email": "user@example.com",
                "name": "Test User",
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = provider.get_user_info("test_access_token")

            assert result.email == "user@example.com"
            assert result.name == "Test User"


class TestGetOAuthProvider:
    """Tests for get_oauth_provider factory."""

    def test_get_google_provider(self):
        """Test getting Google OAuth provider."""
        provider = get_oauth_provider(
            "google", client_id="id", client_secret="secret", redirect_uri="uri"
        )
        assert isinstance(provider, GoogleOAuthProvider)

    def test_get_github_provider(self):
        """Test getting GitHub OAuth provider."""
        provider = get_oauth_provider(
            "github", client_id="id", client_secret="secret", redirect_uri="uri"
        )
        assert isinstance(provider, GitHubOAuthProvider)

    def test_get_oidc_provider(self):
        """Test getting generic OIDC provider."""
        provider = get_oauth_provider(
            "oidc",
            issuer_url="https://issuer.com",
            client_id="id",
            client_secret="secret",
            redirect_uri="uri",
        )
        assert isinstance(provider, OIDCOAuthProvider)


class TestJWTValidator:
    """Tests for JWT validator."""

    def test_validate_jwt_token_valid(self):
        """Test validating a valid JWT token."""

        validator = JWTValidator(secret_key="test_secret")

        # Create a real token that's valid
        token = validator.create_token(
            subject="user123",
            email="user@example.com",
            roles=["user"],
            expires_in=3600,
        )

        result = validator.validate_token(token)
        assert result is not None
        assert result.subject == "user123"
        assert result.email == "user@example.com"

    def test_validate_jwt_token_expired(self):
        """Test validating an expired JWT token."""
        validator = JWTValidator(secret_key="test_secret")

        with patch.object(validator, "_decode_token") as mock_decode:
            mock_decode.side_effect = ValueError("Token expired")

            result = validator.validate_token("expired_token")
            assert result is None

    def test_decode_jwt_payload(self):
        """Test decoding JWT payload."""
        # Test base64 decode logic
        import base64
        import json

        payload = {"sub": "user123", "email": "test@example.com"}
        payload_encoded = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )

        result = decode_jwt_payload(payload_encoded)
        assert result["sub"] == "user123"


class TestSessionManager:
    """Tests for session management."""

    @pytest.fixture
    def session_manager(self):
        """Create session manager with mock Redis."""
        mock_redis = MagicMock()
        return SessionManager(redis_client=mock_redis, session_ttl=3600)

    def test_create_session(self, session_manager):
        """Test creating a session."""
        mock_redis = session_manager._redis
        mock_redis.setex.return_value = True

        session_id = session_manager.create_session(
            user_id="user123",
            email="user@example.com",
            roles=["user"],
        )

        assert session_id is not None
        mock_redis.setex.assert_called_once()

    def test_validate_session_valid(self, session_manager):
        """Test validating a valid session."""
        import time

        mock_redis = session_manager._redis
        import json

        now = int(time.time())
        session_data = json.dumps(
            {
                "session_id": "valid_session_id",
                "user_id": "user123",
                "email": "user@example.com",
                "roles": ["user"],
                "created_at": now,
                "expires_at": now + 3600,
            }
        )
        mock_redis.get.return_value = session_data.encode()

        result = session_manager.validate_session("valid_session_id")

        assert result is not None
        assert result.user_id == "user123"

    def test_validate_session_expired(self, session_manager):
        """Test validating an expired session."""
        mock_redis = session_manager._redis
        mock_redis.get.return_value = None

        result = session_manager.validate_session("expired_session_id")

        assert result is None

    def test_delete_session(self, session_manager):
        """Test deleting a session."""
        mock_redis = session_manager._redis
        mock_redis.delete.return_value = 1

        result = session_manager.delete_session("session_to_delete")

        assert result is True
        mock_redis.delete.assert_called_once()


class TestAuthMiddleware:
    """Tests for authentication middleware."""

    def test_auth_middleware_requires_auth(self):
        """Test that protected endpoints require authentication."""
        try:
            from scheduler.auth.middleware import AuthMiddleware
        except ImportError:
            pytest.skip("AuthMiddleware not implemented yet")

        from unittest.mock import MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/health")
        def health_endpoint():
            return {"status": "ok"}

        @app.get("/protected")
        def protected_endpoint():
            return {"status": "ok"}

        # Add auth middleware with mock session manager
        mock_session_manager = MagicMock()
        mock_session_manager.validate_session.return_value = None

        # Add auth middleware - /health is public, /protected requires auth
        app.add_middleware(
            AuthMiddleware,
            session_manager=mock_session_manager,
            public_paths=["/health"],
            login_url="/login",  # Simple login URL
        )

        # Test that /health is accessible without auth
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

        # Test that /protected redirects to login when no auth
        response = client.get("/protected", follow_redirects=False)
        assert response.status_code in [307, 401]


class TestRBACEnforcement:
    """Tests for RBAC enforcement on gateway endpoints."""

    def test_viewer_cannot_override_run(self):
        """Test that viewer role cannot execute override."""
        from scheduler.auth.rbac import Permission, Role, has_role_permission

        # Viewer should not have override:execute permission
        assert not has_role_permission(Role.VIEWER, Permission.OVERRIDE_EXECUTE)

    def test_operator_can_override_run(self):
        """Test that operator role can execute override."""
        from scheduler.auth.rbac import Permission, Role, has_role_permission

        # Operator should have override:execute permission
        assert has_role_permission(Role.OPERATOR, Permission.OVERRIDE_EXECUTE)

    def test_admin_has_all_permissions(self):
        """Test that admin role has all permissions."""
        from scheduler.auth.rbac import Permission, Role, has_role_permission

        # Admin should have all permissions
        assert has_role_permission(Role.ADMIN, Permission.OVERRIDE_EXECUTE)
        assert has_role_permission(Role.ADMIN, Permission.CRON_TRIGGER)
        assert has_role_permission(Role.ADMIN, Permission.QUEUE_DRAIN)
        assert has_role_permission(Role.ADMIN, Permission.RUNS_READ)
        assert has_role_permission(Role.ADMIN, Permission.ADMIN_ACCESS)

    def test_viewer_can_read_runs(self):
        """Test that viewer role can read runs."""
        from scheduler.auth.rbac import Permission, Role, has_role_permission

        # Viewer should have runs:read permission
        assert has_role_permission(Role.VIEWER, Permission.RUNS_READ)

    def test_viewer_cannot_trigger_cron(self):
        """Test that viewer role cannot trigger cron jobs."""
        from scheduler.auth.rbac import Permission, Role, has_role_permission

        # Viewer should not have cron:trigger permission
        assert not has_role_permission(Role.VIEWER, Permission.CRON_TRIGGER)


class TestJWTConfig:
    """Tests for JWT configuration in RunConfig."""

    def test_auth_config_defaults(self):
        """Test that auth config has correct defaults."""
        import os

        # Set auth env vars for testing
        with patch.dict(os.environ, {"HORDEFORGE_AUTH_ENABLED": "false"}):
            from hordeforge_config import RunConfig

            config = RunConfig.from_env()
            assert config.auth_enabled is False
            assert config.jwt_secret_key == "dev-jwt-secret-change-in-production"
            assert config.jwt_algorithm == "HS256"
            assert config.session_ttl_seconds == 3600
            assert "/health" in config.auth_public_paths

    def test_auth_config_from_env(self):
        """Test that auth config can be set from environment."""
        import os

        env_vars = {
            "HORDEFORGE_AUTH_ENABLED": "true",
            "HORDEFORGE_JWT_SECRET_KEY": "test-secret-key",
            "HORDEFORGE_JWT_ALGORITHM": "HS384",
            "HORDEFORGE_JWT_ISSUER": "test-issuer",
            "HORDEFORGE_JWT_AUDIENCE": "test-audience",
            "HORDEFORGE_SESSION_TTL_SECONDS": "7200",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            from hordeforge_config import RunConfig

            config = RunConfig.from_env()
            assert config.auth_enabled is True
            assert config.jwt_secret_key == "test-secret-key"
            assert config.jwt_algorithm == "HS384"
            assert config.jwt_issuer == "test-issuer"
            assert config.jwt_audience == "test-audience"
            assert config.session_ttl_seconds == 7200


class TestJWTTokenWithRoles:
    """Tests for JWT token with role-based access."""

    def test_create_token_with_admin_role(self):
        """Test creating JWT token with admin role."""
        validator = JWTValidator(secret_key="test_secret")

        token = validator.create_token(
            subject="admin_user",
            email="admin@example.com",
            roles=["admin"],
            expires_in=3600,
        )

        result = validator.validate_token(token)
        assert result is not None
        assert result.subject == "admin_user"
        assert result.roles == ["admin"]

    def test_create_token_with_operator_role(self):
        """Test creating JWT token with operator role."""
        validator = JWTValidator(secret_key="test_secret")

        token = validator.create_token(
            subject="operator_user",
            email="operator@example.com",
            roles=["operator"],
            expires_in=3600,
        )

        result = validator.validate_token(token)
        assert result is not None
        assert result.subject == "operator_user"
        assert result.roles == ["operator"]

    def test_create_token_with_viewer_role(self):
        """Test creating JWT token with viewer role."""
        validator = JWTValidator(secret_key="test_secret")

        token = validator.create_token(
            subject="viewer_user",
            email="viewer@example.com",
            roles=["viewer"],
            expires_in=3600,
        )

        result = validator.validate_token(token)
        assert result is not None
        assert result.subject == "viewer_user"
        assert result.roles == ["viewer"]
