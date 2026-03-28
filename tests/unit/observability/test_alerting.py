from __future__ import annotations

from observability.alerting import SlackConfig, send_slack_alert


def test_send_slack_alert_rejects_non_http_scheme() -> None:
    config = SlackConfig(webhook_url="file:///tmp/alert")

    sent = send_slack_alert(config, message="hello")

    assert sent is False
