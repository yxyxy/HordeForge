from scheduler.gateway import _authorize_manual_command


def test_constant_time_api_key_comparison():
    """Test that API key comparison is constant-time."""
    # Mock the config to have a known API key
    import scheduler.gateway as gw

    original_key = gw.config.operator_api_key
    gw.config.operator_api_key = "test-key-12345"

    try:
        # Test that comparison works correctly
        authorized, reason, _ = _authorize_manual_command(
            operator_key="test-key-12345",
            operator_role="admin",
            command_source="test",
        )
        assert authorized is True
        assert reason is None

        # Test that wrong key is rejected
        authorized, reason, _ = _authorize_manual_command(
            operator_key="wrong-key",
            operator_role="admin",
            command_source="test",
        )
        assert authorized is False
        assert reason == "invalid_operator_key"
    finally:
        gw.config.operator_api_key = original_key
