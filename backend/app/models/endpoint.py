import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
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


def _user_ref() -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class AgentEnrolmentToken(UUIDPrimaryKey, Base):
    """Short-lived secret an IT administrator gives to devices so they can enrol."""

    __tablename__ = "agent_enrolment_tokens"

    organisation_id: Mapped[uuid.UUID] = _org()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # First characters of the token, shown in the UI so people can tell tokens apart.
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    # agent (computers and servers) | collector (on-premises network collector)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="agent", server_default="agent"
    )
    label: Mapped[str | None] = mapped_column(String(120))
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="workstation")
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Agent(UUIDPrimaryKey, Timestamps, Base):
    """A monitoring agent on one device: our reference agent or a Wazuh agent."""

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organisation_id", "source", "external_id"),
        Index("ix_agents_org_status", "organisation_id", "status"),
    )

    organisation_id: Mapped[uuid.UUID] = _org()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # smecm_agent | wazuh | collector
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="smecm_agent")
    # Stable device id from the agent (machine id) or the Wazuh agent id.
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    os_family: Mapped[str | None] = mapped_column(String(16))
    os_name: Mapped[str | None] = mapped_column(String(120))
    os_version: Mapped[str | None] = mapped_column(String(120))
    agent_version: Mapped[str | None] = mapped_column(String(40))
    # active | revoked
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    credential_hash: Mapped[str | None] = mapped_column(String(64))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    enrolled_with: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_enrolment_tokens.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ip: Mapped[str | None] = mapped_column(String(64))
    inventory: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = _user_ref()


class SecurityEvent(UUIDPrimaryKey, Base):
    """A normalised security event from an endpoint. Kept for 30 days, then pruned.

    Raw high-volume telemetry belongs in an event store (OpenSearch evaluation); this table holds
    the normalised events that detections and investigations need.
    """

    __tablename__ = "security_events"
    __table_args__ = (
        UniqueConstraint("agent_id", "source_event_id"),
        Index("ix_security_events_asset_time", "asset_id", "occurred_at"),
        Index("ix_security_events_org_time", "organisation_id", "occurred_at"),
    )

    organisation_id: Mapped[uuid.UUID] = _org()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class IntegrationKey(UUIDPrimaryKey, Base):
    """Organisation-level credential for a connected tool, such as a Wazuh manager."""

    __tablename__ = "integration_keys"

    organisation_id: Mapped[uuid.UUID] = _org()
    # wazuh
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
