from scheduler.auth.middleware import AuthMiddleware


def test_public_path_exact_match_only():
    """Test that public paths use exact matching, not prefix matching."""
    middleware = AuthMiddleware(app=None, public_paths=["/health"])

    # Should pass (exact match)
    assert middleware._is_public_path("/health") is True

    # Should fail (prefix matching bug - these should NOT match)
    assert middleware._is_public_path("/health-secret") is False
    assert middleware._is_public_path("/healthcheck") is False
    assert middleware._is_public_path("/health/") is True  # trailing slash normalized


def test_public_path_root():
    """Test that root path works correctly."""
    middleware = AuthMiddleware(app=None, public_paths=["/"])

    assert middleware._is_public_path("/") is True
    assert middleware._is_public_path("/anything") is False
