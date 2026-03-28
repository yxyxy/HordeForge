import logging

from logging_utils import REDACTED, redact_sensitive_data
from scheduler import gateway


def test_redact_sensitive_data_masks_sensitive_keys():
    payload = {
        "github_token": "ghp_secret_token",
        "nested": {"api_key": "abc123", "safe": "value"},
        "list_items": [{"password": "p@ss"}, {"safe": "ok"}],
    }

    redacted = redact_sensitive_data(payload)

    assert redacted["github_token"] == REDACTED
    assert redacted["nested"]["api_key"] == REDACTED
    assert redacted["nested"]["safe"] == "value"
    assert redacted["list_items"][0]["password"] == REDACTED
    assert redacted["list_items"][1]["safe"] == "ok"


def test_redact_sensitive_data_masks_token_patterns_in_strings():
    payload = {
        "logs": [
            "using token ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "Authorization: Bearer abc.def.ghi",
        ]
    }

    redacted = redact_sensitive_data(payload)

    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in redacted["logs"][0]
    assert "Bearer abc.def.ghi" not in redacted["logs"][1]
    assert REDACTED in redacted["logs"][0]
    assert REDACTED in redacted["logs"][1]


def test_gateway_log_event_redacts_sensitive_fields(caplog):
    caplog.set_level(logging.INFO, logger="hordeforge.gateway")

    gateway._log_event(
        logging.INFO,
        "run-test",
        "redaction_check",
        github_token="ghp_secret_token",
        metadata={"authorization": "Bearer 123", "safe": "ok"},
    )

    log_message = caplog.records[-1].message
    assert "ghp_secret_token" not in log_message
    assert "Bearer 123" not in log_message
    assert REDACTED in log_message
