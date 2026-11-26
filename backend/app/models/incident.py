import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


def _user() -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class Incident(UUIDPrimaryKey, Timestamps, Base):
    """A security incident being investigated and resolved."""

    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("organisation_id", "number"),
        Index("ix_incidents_org_status", "organisation_id", "status"),
    )

    organisation_id: Mapped[uuid.UUID] = _org()
    # Per-organisation running number, shown as INC-0001.
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # critical | high | medium | low
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    # open | investigating | contained | resolved | closed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    # manual | employee_report | correlation
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    owner_id: Mapped[uuid.UUID | None] = _user()
    reported_by: Mapped[uuid.UUID | None] = _user()
    contained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # resolved | false_positive | duplicate | accepted_risk | other
    closure_reason: Mapped[str | None] = mapped_column(String(24))
    resolution_summary: Mapped[str | None] = mapped_column(Text)

    @property
    def reference(self) -> str:
        return f"INC-{self.number:04d}"


class IncidentAsset(Base):
    __tablename__ = "incident_assets"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    organisation_id: Mapped[uuid.UUID] = _org()


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    organisation_id: Mapped[uuid.UUID] = _org()


class IncidentEvent(UUIDPrimaryKey, Base):
    """The incident timeline: everything that happened, in order. Append-only."""

    __tablename__ = "incident_events"
    __table_args__ = (Index("ix_incident_events_incident_time", "incident_id", "occurred_at"),)

    organisation_id: Mapped[uuid.UUID] = _org()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    # created | status_changed | note | evidence_added | alert_linked | asset_linked |
    # assigned | task_added | task_updated | severity_changed | closed | reopened
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = _user()
    actor_label: Mapped[str | None] = mapped_column(String(320))
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentEvidence(UUIDPrimaryKey, Base):
    """A file attached to an incident. Contents live encrypted in object storage."""

    __tablename__ = "incident_evidence"

    organisation_id: Mapped[uuid.UUID] = _org()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RemediationTask(UUIDPrimaryKey, Timestamps, Base):
    """Work to fix a finding or to contain/recover from an incident."""

    __tablename__ = "remediation_tasks"
    __table_args__ = (Index("ix_remediation_tasks_org_status", "organisation_id", "status"),)

    organisation_id: Mapped[uuid.UUID] = _org()
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="SET NULL"), index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    # remediation | containment | recovery
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="remediation")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # critical | high | medium | low
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    # open | in_progress | done | verified | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    assignee_id: Mapped[uuid.UUID | None] = _user()
    created_by: Mapped[uuid.UUID | None] = _user()
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # monitoring (a check confirmed the fix) | manual
    verification: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)


class Report(UUIDPrimaryKey, Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_org_created", "organisation_id", "created_at"),)

    organisation_id: Mapped[uuid.UUID] = _org()
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # pdf | csv
    format: Mapped[str] = mapped_column(String(8), nullable=False, default="pdf")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # ready | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    storage_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
