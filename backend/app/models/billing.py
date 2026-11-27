import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class Subscription(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "subscriptions"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    # trialing | active | past_due | expired | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trialing")
    billing_period: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Key of the last renewal reminder sent (e.g. "2026-12-26T00:00:00+00:00:7"), so each
    # reminder goes out once per period.
    last_reminder: Mapped[str | None] = mapped_column(String(64))


class Payment(UUIDPrimaryKey, Base):
    """One checkout attempt. Paid payments are the organisation's billing history."""

    __tablename__ = "payments"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(16), nullable=False)
    # Amounts are in pesewas (GH₵1 = 100 pesewas) to avoid rounding errors.
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GHS")
    # mobile_money | card
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    # pending | success | failed | abandoned
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    # Safe summary of how it was paid, e.g. {"brand": "visa", "last4": "4081"} or
    # {"network": "MTN", "phone": "*******789"}. Never full card or wallet numbers.
    payment_method: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    receipt_number: Mapped[int | None] = mapped_column(Integer)
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PushDevice(UUIDPrimaryKey, Base):
    """A phone that receives push notifications for the user signed in on it."""

    __tablename__ = "push_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Pushes stop as soon as the session that registered the device ends (sign-out, password
    # change, revocation), so a phone that is signed out never shows alerts.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # android | ios
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(100))
    app_version: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String(200))
