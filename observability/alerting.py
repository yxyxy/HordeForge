from __future__ import annotations

import json
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from logging_utils import redact_mapping

LOGGER = logging.getLogger("hordeforge.alerting")


@dataclass(frozen=True)
class SlackConfig:
    webhook_url: str


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None
    password: str | None
    use_tls: bool


@dataclass(frozen=True)
class AlertingConfig:
    slack: SlackConfig | None
    email: EmailConfig | None


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return ()
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(dict.fromkeys(values))


def load_alerting_config() -> AlertingConfig:
    slack_url = os.getenv("HORDEFORGE_ALERT_SLACK_WEBHOOK", "").strip()
    email_host = os.getenv("HORDEFORGE_ALERT_SMTP_HOST", "").strip()
    email_port = _get_int_env("HORDEFORGE_ALERT_SMTP_PORT", 587)
    email_sender = os.getenv("HORDEFORGE_ALERT_SMTP_SENDER", "").strip()
    email_recipients = _get_csv_env("HORDEFORGE_ALERT_SMTP_RECIPIENTS")
    email_username = os.getenv("HORDEFORGE_ALERT_SMTP_USERNAME", "").strip() or None
    email_password = os.getenv("HORDEFORGE_ALERT_SMTP_PASSWORD", "").strip() or None
    email_use_tls = _get_bool_env("HORDEFORGE_ALERT_SMTP_USE_TLS", True)

    slack = SlackConfig(webhook_url=slack_url) if slack_url else None
    email = None
    if email_host and email_sender and email_recipients:
        email = EmailConfig(
            host=email_host,
            port=email_port,
            sender=email_sender,
            recipients=email_recipients,
            username=email_username,
            password=email_password,
            use_tls=email_use_tls,
        )
    return AlertingConfig(slack=slack, email=email)


def _log_event(level: int, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    payload = {
        "component": "alerting",
        "event": event,
        **safe_fields,
    }
    LOGGER.log(level, json.dumps(payload, ensure_ascii=False))


def _is_allowed_url(url: str) -> bool:
    return urlparse(url).scheme.lower() in {"http", "https"}


def send_slack_alert(config: SlackConfig, *, message: str) -> bool:
    if not _is_allowed_url(config.webhook_url):
        _log_event(logging.ERROR, "slack_alert_failed", error="unsupported_url_scheme")
        return False

    body = json.dumps({"text": message}).encode("utf-8")
    request = Request(
        url=config.webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # nosec B310
            status = response.status
    except URLError as exc:
        _log_event(logging.ERROR, "slack_alert_failed", error=str(exc))
        return False

    if status >= 400:
        _log_event(logging.ERROR, "slack_alert_failed", status=status)
        return False
    _log_event(logging.INFO, "slack_alert_sent", status=status)
    return True


def send_email_alert(config: EmailConfig, *, subject: str, body: str) -> bool:
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(config.host, config.port, timeout=10) as smtp:
            if config.use_tls:
                smtp.starttls()
            if config.username and config.password:
                smtp.login(config.username, config.password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        _log_event(logging.ERROR, "email_alert_failed", error=str(exc))
        return False

    _log_event(logging.INFO, "email_alert_sent")
    return True


def format_alert_message(payload: dict[str, Any]) -> str:
    event = payload.get("event", "alert")
    run_id = payload.get("run_id")
    pipeline_name = payload.get("pipeline_name")
    status = payload.get("status")
    correlation_id = payload.get("correlation_id")
    error = payload.get("error")
    parts = [f"[{event}]", f"pipeline={pipeline_name}", f"status={status}"]
    if run_id:
        parts.append(f"run_id={run_id}")
    if correlation_id:
        parts.append(f"correlation_id={correlation_id}")
    if error:
        parts.append(f"error={error}")
    return " ".join(str(part) for part in parts)
