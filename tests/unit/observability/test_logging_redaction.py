import logging

from logging_utils import REDACTED, redact_sensitive_data
from scheduler import gateway


class _MutatingDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mutated = False

    def items(self):
        if self._mutated:
            return super().items()

        self._mutated = True
        iterator = super().items()

        def _iterate():
            first = True
            for k, v in iterator:
                if first:
                    first = False
                    self["late_field"] = "added_during_iteration"
                yield k, v

        return _iterate()


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
            "using token github_pat_11ABCDEFGHIJKLMNOPQRST_uvwx",
            "Authorization: Bearer abc.def.ghi",
        ]
    }

    redacted = redact_sensitive_data(payload)

    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in redacted["logs"][0]
    assert "github_pat_11ABCDEFGHIJKLMNOPQRST_uvwx" not in redacted["logs"][1]
    assert "Bearer abc.def.ghi" not in redacted["logs"][2]
    assert REDACTED in redacted["logs"][0]
    assert REDACTED in redacted["logs"][1]
    assert REDACTED in redacted["logs"][2]


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


def test_redact_sensitive_data_handles_dict_mutation_during_iteration():
    payload = _MutatingDict({"safe": "ok", "api_key": "secret"})

    redacted = redact_sensitive_data(payload)

    assert redacted["safe"] == "ok"
    assert redacted["api_key"] == REDACTED
