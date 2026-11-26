import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
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
    # trialing | active | past_due | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trialing")
    billing_period: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
