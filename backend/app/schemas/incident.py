import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

Severity = Literal["critical", "high", "medium", "low"]
Category = Literal[
    "malware",
    "phishing",
    "account_compromise",
    "unauthorised_access",
    "intrusion",
    "data_loss",
    "availability",
    "lost_device",
    "policy_violation",
    "other",
]
IncidentStatus = Literal["open", "investigating", "contained", "resolved", "closed"]
ClosureReason = Literal["resolved", "false_positive", "duplicate", "accepted_risk", "other"]
TaskStatus = Literal["open", "in_progress", "done", "verified", "cancelled"]
TaskKind = Literal["remediation", "containment", "recovery"]


def _clean(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("This field is required.")
    return v


class Person(BaseModel):
    id: uuid.UUID
    name: str


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=10000)
    category: Category = "other"
    severity: Severity | None = None
    owner_id: uuid.UUID | None = None
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    alert_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)

    _title = field_validator("title")(lambda cls, v: _clean(v))


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=10000)
    category: Category | None = None
    severity: Severity | None = None
    owner_id: uuid.UUID | None = None
    clear_owner: bool = False
    status: IncidentStatus | None = None
    closure_reason: ClosureReason | None = None
    resolution_summary: str | None = Field(default=None, max_length=10000)


class IncidentOut(ORMModel):
    id: uuid.UUID
    reference: str
    title: str
    summary: str
    severity: str
    status: str
    category: str
    source: str
    owner: Person | None = None
    reporter: Person | None = None
    created_at: datetime
    updated_at: datetime
    contained_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    closure_reason: str | None
    resolution_summary: str | None
    asset_count: int = 0
    alert_count: int = 0
    open_tasks: int = 0


class IncidentAssetOut(BaseModel):
    id: uuid.UUID
    name: str
    identifier: str
    type: str
    criticality: str


class IncidentAlertOut(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    status: str
    asset_name: str
    first_seen_at: datetime


class TimelineEntry(ORMModel):
    id: uuid.UUID
    event_type: str
    actor_label: str | None
    body: str | None
    data: dict
    occurred_at: datetime


class EvidenceOut(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    description: str | None
    created_at: datetime
    uploaded_by_name: str | None = None


class TaskOut(ORMModel):
    id: uuid.UUID
    kind: str
    title: str
    description: str
    priority: str
    status: str
    finding_id: uuid.UUID | None
    incident_id: uuid.UUID | None
    incident_reference: str | None = None
    asset_id: uuid.UUID | None
    asset_name: str | None = None
    assignee: Person | None = None
    due_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    verification: str | None
    note: str | None
    created_at: datetime
    overdue: bool = False


class IncidentDetail(IncidentOut):
    assets: list[IncidentAssetOut]
    alerts: list[IncidentAlertOut]
    timeline: list[TimelineEntry]
    evidence: list[EvidenceOut]
    tasks: list[TaskOut]
    can_manage: bool


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

    _body = field_validator("body")(lambda cls, v: _clean(v))


class LinkAsset(BaseModel):
    asset_id: uuid.UUID


class LinkAlert(BaseModel):
    alert_id: uuid.UUID


class TaskCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    kind: TaskKind = "remediation"
    priority: Severity | None = None
    finding_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: Severity | None = None
    status: TaskStatus | None = None
    assignee_id: uuid.UUID | None = None
    clear_assignee: bool = False
    due_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class RemediationSummary(BaseModel):
    open: int
    in_progress: int
    awaiting_verification: int
    overdue: int
    completed_30d: int
    on_time_rate: int | None
    median_days_to_fix: float | None
    unassigned_urgent_findings: int
