import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey

ASSET_TYPES = (
    "website",
    "domain",
    "workstation",
    "laptop",
    "server",
    "firewall",
    "router",
    "switch",
    "network_device",
    "cloud_account",
    "cloud_service",
)

ASSET_CATEGORIES = {
    "website": "websites_domains",
    "domain": "websites_domains",
    "workstation": "workstations_laptops",
    "laptop": "workstations_laptops",
    "server": "servers",
    "firewall": "firewalls_routers",
    "router": "firewalls_routers",
    "switch": "network_devices",
    "network_device": "network_devices",
    "cloud_account": "cloud",
    "cloud_service": "cloud",
}

EXTERNAL_ASSET_TYPES = {"website", "domain"}
CRITICALITY_LEVELS = ("low", "medium", "high", "critical")
RISK_LEVELS = ("unknown", "low", "medium", "high", "critical")
# not_monitored: registered, authorisation not yet proven
# authorised:    authorisation proven, waiting for a monitoring source (later phases)
# monitoring / degraded / paused: set by the monitoring pipeline
MONITORING_STATUSES = ("not_monitored", "authorised", "monitoring", "degraded", "paused")


class Asset(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_org_type", "organisation_id", "type"),
        Index("ix_assets_org_identifier_lower", "organisation_id", text("lower(identifier)")),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Hostname, URL, IP address, serial number or cloud account ID.
    identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    technology: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    # active | archived
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    monitoring_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_monitored"
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AssetAuthorisation(UUIDPrimaryKey, Base):
    """Evidence that the organisation controls, or is permitted to monitor, an asset."""

    __tablename__ = "asset_authorisations"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # dns_txt | http_file | attestation
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    # Public challenge value. Not a secret: it only proves control when published by the owner.
    challenge: Mapped[str] = mapped_column(String(80), nullable=False)
    # pending | verified | failed | superseded
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
