"""Outbound email.

Outside development, messages go out over SMTP with STARTTLS (any provider: Amazon SES,
Mailgun, Postmark, Zoho, a company mail server). In development they are logged and kept in a
short Redis list that the web app's developer mailbox page reads, so invitations and password
resets can be tested end to end.
"""

import json
import logging
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage

import redis

from app.core.config import settings
from app.core.redis import redis_client

log = logging.getLogger("app.email")
DEV_MAILBOX_KEY = "dev:mailbox"


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.is_development:
        _send_smtp(to, subject, body)
        return
    log.info("DEV EMAIL to=%s subject=%s\n%s", to, subject, body)
    message = {
        "to": to,
        "subject": subject,
        "body": body,
        "sent_at": datetime.now(UTC).isoformat(),
    }
    try:
        redis_client.lpush(DEV_MAILBOX_KEY, json.dumps(message))
        redis_client.ltrim(DEV_MAILBOX_KEY, 0, 49)
    except redis.RedisError:
        log.warning("Could not store development email")


def read_dev_mailbox() -> list[dict]:
    try:
        return [json.loads(m) for m in redis_client.lrange(DEV_MAILBOX_KEY, 0, 49)]
    except redis.RedisError:
        return []


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException):
        # Never log the body: it may contain a one-time link.
        log.exception("Could not send email to %s (%s)", to, subject)
