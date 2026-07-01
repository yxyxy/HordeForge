import pytest

from scheduler.auth.session_manager import SessionManager


def test_jwt_secret_required():
    """Test that JWT secret is required."""
    with pytest.raises(ValueError, match="jwt_secret must be provided"):
        SessionManager(jwt_secret=None)


def test_jwt_secret_provided():
    """Test that JWT secret can be provided."""
    manager = SessionManager(jwt_secret="test-secret-key")
    assert manager.jwt_secret == "test-secret-key"
