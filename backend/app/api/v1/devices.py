"""Phones registered for push notifications. These belong to a person, not an organisation."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.config import settings
from app.core.db import get_db, system_context
from app.core.errors import APIError
from app.core.redis import rate_limit
from app.models import AuthSession, PushDevice
from app.schemas.common import Message
from app.security.tokens import encrypt_secret, hash_token
from app.services import audit, push

router = APIRouter(prefix="/me", tags=["Mobile devices"])


class DeviceRegister(BaseModel):
    platform: Literal["android", "ios"]
    token: str = Field(min_length=20, max_length=4096)
    device_name: str | None = Field(default=None, max_length=100)
    app_version: str | None = Field(default=None, max_length=32)


class DeviceOut(BaseModel):
    id: uuid.UUID
    platform: str
    device_name: str | None
    app_version: str | None
    enabled: bool
    this_device: bool
    created_at: datetime
    last_seen_at: datetime
    last_error: str | None


def _out(d: PushDevice, auth: AuthContext) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        platform=d.platform,
        device_name=d.device_name,
        app_version=d.app_version,
        enabled=d.enabled,
        this_device=d.session_id == auth.session.id,
        created_at=d.created_at,
        last_seen_at=d.last_seen_at,
        last_error=d.last_error,
    )


@router.post("/push-devices", response_model=DeviceOut, status_code=201)
def register_device(
    body: DeviceRegister,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> DeviceOut:
    """Register (or refresh) this phone's push token for the signed-in person."""
    rate_limit(f"push-register:{auth.user.id}", limit=30, window_seconds=3600)
    token_hash = hash_token(body.token)
    # The same phone may have been used by someone else before. Hand the token over only once
    # that person's session on it has ended; otherwise anyone who learned a token could
    # silently stop another person's security alerts.
    now = datetime.now(UTC)
    with system_context(db):
        device = db.scalar(select(PushDevice).where(PushDevice.token_hash == token_hash))
        if device is not None and device.user_id != auth.user.id:
            previous = db.get(AuthSession, device.session_id) if device.session_id else None
            if (
                previous is not None
                and previous.revoked_at is None
                and previous.expires_at > now
                and device.enabled
            ):
                raise APIError(
                    409,
                    "device_in_use",
                    "This phone is still signed in to another account. Sign that account out "
                    "first.",
                )
            db.delete(device)
            db.flush()
            device = None
    created = device is None
    if device is None:
        device = PushDevice(
            user_id=auth.user.id,
            token_hash=token_hash,
            token_encrypted=encrypt_secret(body.token),
            platform=body.platform,
        )
        db.add(device)
    device.session_id = auth.session.id
    device.platform = body.platform
    device.device_name = body.device_name
    device.app_version = body.app_version
    device.enabled = True
    device.last_error = None
    device.last_seen_at = now
    db.flush()
    if created:
        audit.record(
            db,
            "user.push_device_registered",
            actor=auth.user,
            resource_type="push_device",
            resource_id=device.id,
            details={"platform": body.platform, "device": body.device_name},
            request=request,
        )
    db.commit()
    return _out(device, auth)


@router.get("/push-devices", response_model=list[DeviceOut])
def list_devices(
    auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> list[DeviceOut]:
    rows = db.scalars(
        select(PushDevice)
        .where(PushDevice.user_id == auth.user.id)
        .order_by(PushDevice.last_seen_at.desc())
    )
    return [_out(d, auth) for d in rows]


@router.delete("/push-devices/{device_id}", response_model=Message)
def remove_device(
    device_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> Message:
    device = db.get(PushDevice, device_id)
    if device is None or device.user_id != auth.user.id:
        raise APIError(404, "not_found", "Device not found.")
    db.delete(device)
    audit.record(
        db,
        "user.push_device_removed",
        actor=auth.user,
        resource_type="push_device",
        resource_id=device_id,
        request=request,
    )
    db.commit()
    return Message(message="Device removed.")


@router.post("/push-devices/test", response_model=Message)
def test_push(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> Message:
    """Send a test notification to the caller's phones."""
    rate_limit(f"push-test:{auth.user.id}", limit=5, window_seconds=600)
    devices = push.live_devices(db, auth.user.id)
    if not devices:
        raise APIError(
            404,
            "no_devices",
            "No phone is registered. Sign in to the mobile app and allow notifications.",
        )
    message = push.PushMessage(
        title=settings.brand_product_name,
        body="Test notification: push alerts are working on this device.",
        data={"link": "/notifications"},
    )
    sent = sum(1 for d in devices if push.send_to_device(db, d, message))
    db.commit()
    if not sent:
        raise APIError(502, "push_failed", "The notification could not be delivered. Try again.")
    return Message(message=f"Sent to {sent} device{'s' if sent != 1 else ''}.")
