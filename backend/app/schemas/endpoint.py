"""Schemas for devices and agents.

Agent-facing models use ``extra="forbid"``: telemetry with unexpected fields (for example a forged
``organisation_id``) is rejected outright rather than silently ignored.
"""

import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel

OSFamily = Literal["windows", "macos", "linux", "other"]
EventType = Literal[
    "authentication.failure",
    "authentication.success",
    "malware.detected",
    "protection.disabled",
    "account.privileged_created",
    "log.cleared",
    "process.suspicious",
    "removable_media.connected",
    "file_integrity.changed",
    "generic",
]
EventSeverity = Literal["critical", "high", "medium", "low", "informational"]
EnrolAssetType = Literal["workstation", "laptop", "server"]

MAX_EVENT_DATA_BYTES = 8192
MAX_EVENTS_PER_BATCH = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Inventory(Strict):
    hostname: str = Field(min_length=1, max_length=255)
    os_family: OSFamily
    os_name: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=120)
    kernel: str | None = Field(default=None, max_length=120)
    architecture: str | None = Field(default=None, max_length=40)
    uptime_seconds: int | None = Field(default=None, ge=0)
    ip_addresses: list[str] = Field(default_factory=list, max_length=20)
    cpu_count: int | None = Field(default=None, ge=0, le=4096)
    memory_total_mb: int | None = Field(default=None, ge=0)
    disk_total_gb: float | None = Field(default=None, ge=0)
    disk_used_percent: float | None = Field(default=None, ge=0, le=100)
    antivirus_enabled: bool | None = None
    antivirus_name: str | None = Field(default=None, max_length=120)
    firewall_enabled: bool | None = None
    disk_encrypted: bool | None = None
    pending_updates: int | None = Field(default=None, ge=0)
    pending_security_updates: int | None = Field(default=None, ge=0)
    reboot_required: bool | None = None
    logged_in_users: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("ip_addresses", "logged_in_users")
    @classmethod
    def _short_items(cls, v: list[str]) -> list[str]:
        return [item[:64] for item in v]


class EnrolRequest(Strict):
    token: str = Field(min_length=10, max_length=200)
    machine_id: str = Field(min_length=6, max_length=128)
    agent_version: str = Field(min_length=1, max_length=40)
    inventory: Inventory


class EnrolResponse(BaseModel):
    agent_id: uuid.UUID
    credential: str
    heartbeat_seconds: int
    server_time: datetime


class HeartbeatRequest(Strict):
    agent_version: str = Field(min_length=1, max_length=40)
    inventory: Inventory


class HeartbeatResponse(BaseModel):
    status: str
    heartbeat_seconds: int
    server_time: datetime


class EventIn(Strict):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: EventType
    timestamp: datetime
    severity: EventSeverity | None = None
    summary: str | None = Field(default=None, max_length=300)
    data: dict = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def _bounded(cls, v: dict) -> dict:
        if len(json.dumps(v, default=str)) > MAX_EVENT_DATA_BYTES:
            raise ValueError(f"Event data must be under {MAX_EVENT_DATA_BYTES} bytes.")
        return v


class EventBatch(Strict):
    events: list[EventIn] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)


class EventBatchResult(BaseModel):
    accepted: int
    duplicates: int


# --- Management (web app) ------------------------------------------------------------------


class TokenCreate(BaseModel):
    kind: Literal["agent", "collector"] = "agent"
    label: str | None = Field(default=None, max_length=120)
    asset_type: EnrolAssetType = "workstation"
    department_id: uuid.UUID | None = None
    valid_hours: int = Field(default=24, ge=1, le=168)
    max_uses: int = Field(default=1, ge=1, le=500)


class TokenOut(ORMModel):
    id: uuid.UUID
    kind: str
    token_hint: str
    label: str | None
    asset_type: str
    department_id: uuid.UUID | None
    max_uses: int
    uses: int
    created_at: datetime
    expires_at: datetime


class TokenCreated(BaseModel):
    token: str
    details: TokenOut


class EndpointAsset(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    department_name: str | None
    criticality: str


class EndpointOut(BaseModel):
    id: uuid.UUID
    source: str
    hostname: str
    os_family: str | None
    os_name: str | None
    os_version: str | None
    agent_version: str | None
    status: str
    online: bool
    last_seen_at: datetime | None
    last_ip: str | None
    enrolled_at: datetime
    inventory: dict
    asset: EndpointAsset
    open_alerts: int
    open_findings: int
    events_24h: int


class EndpointSummary(BaseModel):
    total: int
    online: int
    offline: int
    with_issues: int
    events_24h: int


class SecurityEventOut(ORMModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    agent_id: uuid.UUID
    event_type: str
    severity: str
    summary: str
    occurred_at: datetime
    received_at: datetime
    data: dict
    asset_name: str | None = None


class IntegrationKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["wazuh"] = "wazuh"


class IntegrationKeyOut(ORMModel):
    id: uuid.UUID
    kind: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None


class IntegrationKeyCreated(BaseModel):
    key: str
    details: IntegrationKeyOut


class AgentRelease(BaseModel):
    version: str
    filename: str
    sha256: str
    size_bytes: int
