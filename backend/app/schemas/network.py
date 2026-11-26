"""Schemas for on-premises network collectors. Collector payloads reject unexpected fields."""

import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.endpoint import MAX_EVENT_DATA_BYTES, EventSeverity, Strict

NetworkEventType = Literal[
    "network.firewall_deny",
    "network.config_change",
    "network.admin_login_failure",
    "network.admin_login_success",
    "network.vpn_login",
    "network.ids_alert",
    "network.zeek_notice",
]
Capability = Literal["syslog_udp", "syslog_tcp", "suricata", "zeek", "probe"]


class SourceStatus(Strict):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["syslog", "suricata", "zeek"]
    events: int = Field(ge=0)
    last_event_at: datetime | None = None


class CollectorHealth(Strict):
    hostname: str = Field(min_length=1, max_length=255)
    uptime_seconds: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    events_dropped: int = Field(ge=0, description="Events dropped since the previous heartbeat")
    events_forwarded: int = Field(ge=0, description="Events forwarded since the previous heartbeat")
    capabilities: list[Capability] = Field(default_factory=list, max_length=10)
    sources: list[SourceStatus] = Field(default_factory=list, max_length=50)
    listen: dict[str, int] = Field(default_factory=dict)

    @field_validator("listen")
    @classmethod
    def _ports(cls, v: dict[str, int]) -> dict[str, int]:
        if len(v) > 5 or any(not (0 < p < 65536) for p in v.values()):
            raise ValueError("Invalid listener ports.")
        return v


class ProbeResult(Strict):
    asset_id: uuid.UUID
    reachable: bool
    latency_ms: float | None = Field(default=None, ge=0, le=60000)
    method: str | None = Field(default=None, max_length=20)


class TrafficSummary(Strict):
    window_seconds: int = Field(ge=1, le=86400)
    connections: int = Field(ge=0)
    bytes_in: int = Field(ge=0)
    bytes_out: int = Field(ge=0)
    top_talkers: list[dict] = Field(default_factory=list, max_length=10)


class CollectorEnrol(Strict):
    token: str = Field(min_length=10, max_length=200)
    machine_id: str = Field(min_length=6, max_length=128)
    version: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=120)
    health: CollectorHealth


class CollectorHeartbeat(Strict):
    version: str = Field(min_length=1, max_length=40)
    health: CollectorHealth
    probes: list[ProbeResult] = Field(default_factory=list, max_length=500)
    traffic: TrafficSummary | None = None


class ProbeTarget(BaseModel):
    asset_id: uuid.UUID
    name: str
    address: str
    type: str


class CollectorHeartbeatResponse(BaseModel):
    status: str
    heartbeat_seconds: int
    probe_seconds: int
    probe_targets: list[ProbeTarget]
    server_time: datetime


class CollectorEnrolResponse(CollectorHeartbeatResponse):
    collector_id: uuid.UUID
    credential: str


class NetworkEventIn(Strict):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: NetworkEventType
    timestamp: datetime
    severity: EventSeverity | None = None
    summary: str | None = Field(default=None, max_length=300)
    device: str | None = Field(default=None, max_length=255)
    count: int = Field(default=1, ge=1, le=1_000_000)
    data: dict = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def _bounded(cls, v: dict) -> dict:
        if len(json.dumps(v, default=str)) > MAX_EVENT_DATA_BYTES:
            raise ValueError(f"Event data must be under {MAX_EVENT_DATA_BYTES} bytes.")
        return v


class NetworkEventBatch(Strict):
    events: list[NetworkEventIn] = Field(min_length=1, max_length=500)


# --- People-facing -------------------------------------------------------------------------


class CollectorOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    name: str
    hostname: str
    version: str | None
    status: str
    online: bool
    last_seen_at: datetime | None
    last_ip: str | None
    enrolled_at: datetime
    capabilities: list[str]
    sources: list[dict]
    queue_depth: int | None
    events_24h: int
    traffic: dict | None


class NetworkDeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    identifier: str
    type: str
    criticality: str
    monitoring_status: str
    availability: str  # reachable | unreachable | not_probed | awaiting_authorisation
    latency_ms: float | None
    last_seen_at: datetime | None
    last_checked_at: datetime | None
    open_findings: int
    events_24h: int


class Signature(BaseModel):
    name: str
    count: int
    severity: str


class NetworkSummary(BaseModel):
    collectors_total: int
    collectors_online: int
    collector_allowance: int | None
    devices_total: int
    devices_reachable: int
    devices_unreachable: int
    devices_not_probed: int
    sensor_deployed: bool
    ids_alerts_24h: dict[str, int]
    firewall_denies_24h: int
    config_changes_24h: int
    top_signatures: list[Signature]
    traffic: dict | None
