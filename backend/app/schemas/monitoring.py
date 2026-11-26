import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

CheckType = Literal["uptime", "tls", "security_headers", "dns", "email_security"]
Severity = Literal["critical", "high", "medium", "low", "informational"]


class AssetRef(BaseModel):
    id: uuid.UUID
    name: str
    identifier: str
    type: str
    criticality: str


class CheckOut(ORMModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    check_type: str
    interval_minutes: int
    enabled: bool
    next_run_at: datetime
    last_run_at: datetime | None
    last_status: str
    last_summary: str | None
    consecutive_failures: int
    asset: AssetRef | None = None


class CheckCreate(BaseModel):
    asset_id: uuid.UUID
    check_type: CheckType


class CheckUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None


class RunOut(ORMModel):
    id: uuid.UUID
    check_id: uuid.UUID
    asset_id: uuid.UUID
    check_type: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: str
    summary: str
    result: dict


class MonitoringSummary(BaseModel):
    checks_total: int
    checks_enabled: int
    by_status: dict[str, int]
    monitored_assets: int
    monitorable_assets: int
    awaiting_authorisation: int
    assets_with_check_errors: int


class FindingOut(ORMModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    check_type: str
    rule_key: str
    title: str
    description: str
    impact: str
    recommendation: str
    severity: str
    score: int
    status: str
    evidence: dict
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None
    asset: AssetRef | None = None


class FindingDetail(FindingOut):
    open_alert_id: uuid.UUID | None = None
    sticky: bool = False
    resolved_by_name: str | None = None


class FindingUpdate(BaseModel):
    status: Literal["open", "resolved", "accepted_risk"]
    note: str | None = Field(default=None, max_length=1000)


class AlertOut(ORMModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    asset_id: uuid.UUID
    title: str
    severity: str
    status: str
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    asset: AssetRef | None = None


class AlertDetail(AlertOut):
    finding: FindingOut
    acknowledged_by_name: str | None = None
    resolved_by_name: str | None = None


class AlertUpdate(BaseModel):
    status: Literal["new", "acknowledged", "investigating", "resolved"]
    note: str | None = Field(default=None, max_length=1000)


class NotificationOut(ORMModel):
    id: uuid.UUID
    alert_id: uuid.UUID | None
    severity: str | None
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class MarkRead(BaseModel):
    ids: list[uuid.UUID] | None = None


NotifyLevel = Literal["critical", "high", "medium", "low", "off"]


class NotificationPreferences(BaseModel):
    email_min_severity: NotifyLevel = "high"
    in_app_min_severity: NotifyLevel = "low"


class TrendPoint(BaseModel):
    day: date
    score: int
