"""Mobile push notifications.

The monitoring engine and incident service already write an in-app :class:`Notification` for
every person who should hear about something. The monitor worker turns new ones into pushes
(``dispatch_pending``), so push follows exactly the same audience and permission rules, and a
slow or unavailable push service can never hold up detection.

Providers:

* ``log``: development. Pushes are logged and kept in a short Redis list (``/dev/push``).
* ``fcm``: Firebase Cloud Messaging HTTP v1, which delivers to Android directly and to iOS
  through APNs. Authenticates with a Google service-account key.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import redis_client
from app.models import AuthSession, Notification, NotificationPreference, Organisation, PushDevice
from app.monitoring.catalogue import severity_rank
from app.security.tokens import decrypt_secret

log = logging.getLogger("app.push")
DEV_PUSH_KEY = "dev:push"
# Older notifications are not pushed: a phone buzzing about something from yesterday (for
# example after the push service was down) is noise, and the in-app inbox already has it.
MAX_AGE = timedelta(minutes=30)
BATCH = 200


@dataclass
class PushMessage:
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)
    severity: str | None = None


class InvalidToken(Exception):
    """The device token is no longer valid (app uninstalled or token rotated)."""


class LogProvider:
    name = "log"

    def send(self, token: str, platform: str, message: PushMessage) -> None:
        log.info("DEV PUSH platform=%s title=%s body=%s", platform, message.title, message.body)
        record = {
            "token_tail": token[-6:],
            "platform": platform,
            "title": message.title,
            "body": message.body,
            "data": message.data,
            "sent_at": datetime.now(UTC).isoformat(),
        }
        try:
            redis_client.lpush(DEV_PUSH_KEY, json.dumps(record))
            redis_client.ltrim(DEV_PUSH_KEY, 0, 49)
        except redis.RedisError:
            log.warning("Could not store development push")


class FCMProvider:
    name = "fcm"
    _token: tuple[str, float] | None = None

    def __init__(self) -> None:
        with open(settings.fcm_service_account_file) as fh:
            self.account = json.load(fh)
        self.project_id = settings.fcm_project_id or self.account["project_id"]

    def _access_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self.account["client_email"],
                "scope": "https://www.googleapis.com/auth/firebase.messaging",
                "aud": self.account["token_uri"],
                "iat": now,
                "exp": now + 3600,
            },
            self.account["private_key"],
            algorithm="RS256",
        )
        resp = httpx.post(
            self.account["token_uri"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = (data["access_token"], time.time() + data.get("expires_in", 3600))
        return self._token[0]

    def send(self, token: str, platform: str, message: PushMessage) -> None:
        urgent = message.severity in {"critical", "high"}
        payload = {
            "message": {
                "token": token,
                "notification": {"title": message.title, "body": message.body},
                "data": message.data,
                "android": {
                    "priority": "high" if urgent else "normal",
                    "notification": {"channel_id": "security_alerts" if urgent else "updates"},
                },
                "apns": {
                    "headers": {"apns-priority": "10" if urgent else "5"},
                    "payload": {"aps": {"sound": "default"}},
                },
            }
        }
        resp = httpx.post(
            f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
            json=payload,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=15,
        )
        if resp.status_code in (400, 404):
            detail = resp.text
            if "UNREGISTERED" in detail or "INVALID_ARGUMENT" in detail or resp.status_code == 404:
                raise InvalidToken(detail[:200])
        resp.raise_for_status()


_provider: LogProvider | FCMProvider | None = None


def get_provider() -> LogProvider | FCMProvider:
    global _provider
    if _provider is None:
        _provider = FCMProvider() if settings.push_provider == "fcm" else LogProvider()
    return _provider


def read_dev_pushes() -> list[dict]:
    try:
        return [json.loads(m) for m in redis_client.lrange(DEV_PUSH_KEY, 0, 49)]
    except redis.RedisError:
        return []


def build_message(notification: Notification, org_name: str) -> PushMessage:
    severity = (notification.severity or "").capitalize()
    title = f"{severity} · {org_name}" if severity else org_name
    body = notification.title
    if settings.push_include_details:
        body = f"{notification.title}\n{notification.body}"
    return PushMessage(
        title=title[:120],
        body=body[:240],
        severity=notification.severity,
        data={
            "notification_id": str(notification.id),
            "organisation_id": str(notification.organisation_id),
            "link": notification.link or "",
        },
    )


def live_devices(db: Session, user_id: uuid.UUID) -> list[PushDevice]:
    """Enabled devices whose signing-in session is still valid."""
    now = datetime.now(UTC)
    return list(
        db.scalars(
            select(PushDevice)
            .join(AuthSession, AuthSession.id == PushDevice.session_id)
            .where(
                PushDevice.user_id == user_id,
                PushDevice.enabled.is_(True),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
    )


def send_to_device(db: Session, device: PushDevice, message: PushMessage) -> bool:
    token = decrypt_secret(device.token_encrypted)
    if not token:
        device.enabled = False
        device.last_error = "Token could not be decrypted"
        return False
    try:
        get_provider().send(token, device.platform, message)
        device.last_error = None
        return True
    except InvalidToken:
        device.enabled = False
        device.last_error = "The app was uninstalled or signed out on this device"
    except Exception as exc:  # noqa: BLE001 - one failing device must not stop the batch
        log.warning("push to device %s failed: %s", device.id, exc)
        device.last_error = str(exc)[:200]
    return False


def dispatch_pending(db: Session, now: datetime | None = None) -> int:
    """Push new notifications to each recipient's phones. Runs in system context."""
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(Notification, NotificationPreference.push_min_severity, Organisation.name)
        .join(Organisation, Organisation.id == Notification.organisation_id)
        .outerjoin(
            NotificationPreference,
            (NotificationPreference.user_id == Notification.user_id)
            & (NotificationPreference.organisation_id == Notification.organisation_id),
        )
        .where(Notification.pushed_at.is_(None))
        .order_by(Notification.created_at)
        .limit(BATCH)
        .with_for_update(of=Notification, skip_locked=True)
    ).all()
    sent = 0
    devices_by_user: dict[uuid.UUID, list[PushDevice]] = {}
    for notification, push_min, org_name in rows:
        notification.pushed_at = now
        if notification.created_at < now - MAX_AGE:
            continue
        threshold = push_min or "high"
        if threshold == "off" or (
            notification.severity
            and severity_rank(notification.severity) < severity_rank(threshold)
        ):
            continue
        if notification.user_id not in devices_by_user:
            devices_by_user[notification.user_id] = live_devices(db, notification.user_id)
        message = build_message(notification, org_name)
        for device in devices_by_user[notification.user_id]:
            if device.enabled and send_to_device(db, device, message):
                sent += 1
    db.commit()
    return sent
