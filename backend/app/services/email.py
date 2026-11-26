"""Outbound email.

Milestone 1 has no email provider. In development, messages are logged and kept in a
short Redis list that the web app's developer mailbox page reads, so invitations and
password resets can be tested end to end. A real provider is wired in with notifications.
"""

import json
import logging
from datetime import UTC, datetime

import redis

from app.core.config import settings
from app.core.redis import redis_client

log = logging.getLogger("app.email")
DEV_MAILBOX_KEY = "dev:mailbox"


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.is_development:
        # Never log message bodies outside development: they contain one-time links.
        log.warning("No email provider configured; message to %s not sent", to)
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
