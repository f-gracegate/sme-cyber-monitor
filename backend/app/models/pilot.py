"""Pilot-programme and data-protection records (Phase 7)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )


def _user() -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SuppressionRule(UUIDPrimaryKey, Base):
    """Mutes alerts for a known, accepted condition. Findings are still recorded."""

    __tablename__ = "suppression_rules"
    __table_args__ = (Index("ix_suppression_org_rule", "organisation_id", "rule_key"),)

    organisation_id: Mapped[uuid.UUID] = _org()
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # None = every asset in the organisation.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _now()
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(UUIDPrimaryKey, Base):
    """What pilot customers tell us from inside the product."""

    __tablename__ = "feedback"

    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = _user()
    # idea | problem | praise | question
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str | None] = mapped_column(String(200))
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    # new | reviewed | done
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    created_at: Mapped[datetime] = _now()


class DataExport(UUIDPrimaryKey, Base):
    """A copy of an organisation's data, for portability and data-subject requests (Act 843)."""

    __tablename__ = "data_exports"

    organisation_id: Mapped[uuid.UUID] = _org()
    requested_by: Mapped[uuid.UUID | None] = _user()
    # ready | failed | expired
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    storage_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
