import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


def _asset_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )


class MonitoringCheck(UUIDPrimaryKey, Timestamps, Base):
    """A scheduled check of one asset, e.g. uptime of a website every 5 minutes."""

    __tablename__ = "monitoring_checks"
    __table_args__ = (
        UniqueConstraint("asset_id", "check_type"),
        Index("ix_monitoring_checks_due", "enabled", "next_run_at"),
    )

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    asset_id: Mapped[uuid.UUID] = _asset_fk()
    # uptime | tls | security_headers | dns | email_security
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # pending | ok | warning | failing | error
    last_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    last_summary: Mapped[str | None] = mapped_column(String(400))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Values carried between runs, e.g. the previous set of nameservers.
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class CheckRun(UUIDPrimaryKey, Base):
    __tablename__ = "check_runs"
    __table_args__ = (Index("ix_check_runs_check_started", "check_id", "started_at"),)

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    asset_id: Mapped[uuid.UUID] = _asset_fk()
    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_checks.id", ondelete="CASCADE"), nullable=False
    )
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Finding(UUIDPrimaryKey, Base):
    """A security weakness or condition detected on an asset. One row per asset and rule."""

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("asset_id", "rule_key"),
        Index("ix_findings_org_status", "organisation_id", "status"),
    )

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    asset_id: Mapped[uuid.UUID] = _asset_fk()
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    # critical | high | medium | low | informational
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # open | resolved | accepted_risk
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL with resolved_at set means the system saw the condition clear.
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution_note: Mapped[str | None] = mapped_column(String(1000))


class Alert(UUIDPrimaryKey, Base):
    """Something that needs a person's attention. Repeats of the same finding are grouped."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_org_status", "organisation_id", "status"),
        # At most one unresolved alert per finding: this is what deduplicates repeats.
        Index(
            "uq_alerts_open_per_finding",
            "finding_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    asset_id: Mapped[uuid.UUID] = _asset_fk()
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # new | acknowledged | investigating | resolved
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution_note: Mapped[str | None] = mapped_column(String(1000))


class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_org_created", "user_id", "organisation_id"),)

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE")
    )
    severity: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    link: Mapped[str | None] = mapped_column(String(300))
    emailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set once the push dispatcher has handled this notification (sent or skipped).
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationPreference(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("organisation_id", "user_id"),)

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # critical | high | medium | low | off
    email_min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="high")
    in_app_min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    push_min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="high")


class RiskScoreSnapshot(UUIDPrimaryKey, Base):
    """One posture score per organisation per day, for the trend chart."""

    __tablename__ = "risk_score_history"
    __table_args__ = (UniqueConstraint("organisation_id", "day"),)

    organisation_id: Mapped[uuid.UUID] = _org_fk()
    day: Mapped[date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    open_critical: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_high: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_medium: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_low: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monitored_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Breakdown of the score (component -> 0..100) and how much of the estate it's based on.
    components: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
