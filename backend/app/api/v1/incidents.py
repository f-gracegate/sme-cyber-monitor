"""Incident management and remediation tasks."""

import hashlib
import re
import statistics
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.core.config import settings
from app.core.db import get_db, system_context
from app.core.errors import APIError, forbidden, not_found
from app.incidents import service
from app.models import (
    Alert,
    Asset,
    Finding,
    Incident,
    IncidentAlert,
    IncidentAsset,
    IncidentEvent,
    IncidentEvidence,
    Membership,
    Notification,
    RemediationTask,
    User,
)
from app.monitoring.engine import EmailJob
from app.schemas.common import Page
from app.schemas.incident import (
    EvidenceOut,
    IncidentAlertOut,
    IncidentAssetOut,
    IncidentCreate,
    IncidentDetail,
    IncidentOut,
    IncidentUpdate,
    LinkAlert,
    LinkAsset,
    NoteCreate,
    Person,
    RemediationSummary,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TimelineEntry,
)
from app.security.rbac import Perm
from app.services import audit, storage
from app.services.email import send_email

router = APIRouter()

EVIDENCE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".eml",
    ".msg",
    ".pcap",
    ".pcapng",
    ".zip",
    ".xml",
    ".html",
    ".docx",
    ".xlsx",
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _send(mails) -> None:
    for m in mails:
        send_email(m.to, m.subject, m.body)


def _person(db: Session, user_id) -> Person | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return Person(id=user.id, name=user.full_name or user.email) if user else None


def _member(db: Session, ctx: OrgContext, user_id: uuid.UUID) -> User:
    exists = db.scalar(
        select(Membership.id).where(
            Membership.organisation_id == ctx.org_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
    )
    if not exists:
        raise APIError(422, "validation_error", "Choose an active member of this organisation.")
    return db.get(User, user_id)


def _incident_out(db: Session, inc: Incident) -> IncidentOut:
    return IncidentOut.model_validate(inc).model_copy(
        update={
            "reference": inc.reference,
            "owner": _person(db, inc.owner_id),
            "reporter": _person(db, inc.reported_by),
            "asset_count": db.scalar(
                select(func.count()).where(IncidentAsset.incident_id == inc.id)
            )
            or 0,
            "alert_count": db.scalar(
                select(func.count()).where(IncidentAlert.incident_id == inc.id)
            )
            or 0,
            "open_tasks": db.scalar(
                select(func.count()).where(
                    RemediationTask.incident_id == inc.id,
                    RemediationTask.status.in_(("open", "in_progress")),
                )
            )
            or 0,
        }
    )


def _task_out(db: Session, task: RemediationTask, now: datetime | None = None) -> TaskOut:
    now = now or datetime.now(UTC)
    incident = db.get(Incident, task.incident_id) if task.incident_id else None
    asset = db.get(Asset, task.asset_id) if task.asset_id else None
    return TaskOut.model_validate(task).model_copy(
        update={
            "assignee": _person(db, task.assignee_id),
            "incident_reference": incident.reference if incident else None,
            "asset_name": asset.name if asset else None,
            "overdue": bool(
                task.due_at and task.due_at < now and task.status in ("open", "in_progress")
            ),
        }
    )


def _load_incident(db: Session, ctx: OrgContext, incident_id: uuid.UUID) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None or inc.organisation_id != ctx.org_id:
        raise not_found("Incident")
    if not ctx.has(Perm.INCIDENTS_READ) and inc.reported_by != ctx.user.id:
        raise not_found("Incident")  # reporters only see their own reports
    return inc


def _require_manage(ctx: OrgContext) -> None:
    if not ctx.has(Perm.INCIDENTS_MANAGE):
        raise forbidden()


# --- Incidents -----------------------------------------------------------------------------


@router.get("/incidents", response_model=Page[IncidentOut], tags=["Incidents"])
def list_incidents(
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
    status: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    mine: bool = False,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[IncidentOut]:
    stmt = select(Incident).where(Incident.organisation_id == ctx.org_id)
    if not ctx.has(Perm.INCIDENTS_READ):
        stmt = stmt.where(Incident.reported_by == ctx.user.id)
    if status:
        stmt = stmt.where(Incident.status.in_(status))
    if severity:
        stmt = stmt.where(Incident.severity.in_(severity))
    if mine:
        stmt = stmt.where(Incident.owner_id == ctx.user.id)
    if q:
        ref = re.fullmatch(r"inc-?0*(\d{1,9})", q.strip(), re.IGNORECASE)
        if ref:
            stmt = stmt.where(Incident.number == int(ref.group(1)))
        else:
            stmt = stmt.where(Incident.title.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Incident.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[IncidentOut](
        items=[_incident_out(db, i) for i in rows], total=total, page=page, page_size=page_size
    )


@router.post("/incidents", response_model=IncidentOut, status_code=201, tags=["Incidents"])
def create_incident(
    body: IncidentCreate,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
) -> IncidentOut:
    manager = ctx.has(Perm.INCIDENTS_MANAGE)
    for asset_id in body.asset_ids:
        asset = db.get(Asset, asset_id)
        if asset is None or asset.organisation_id != ctx.org_id:
            raise APIError(422, "validation_error", "Choose assets from this organisation.")
    alerts = []
    for alert_id in body.alert_ids if manager else []:
        alert = db.get(Alert, alert_id)
        if alert is None or alert.organisation_id != ctx.org_id:
            raise APIError(422, "validation_error", "Choose alerts from this organisation.")
        alerts.append(alert)
    owner = _member(db, ctx, body.owner_id).id if manager and body.owner_id else None
    incident, mails = service.create_incident(
        db,
        ctx.org_id,
        title=body.title,
        summary=body.summary.strip(),
        severity=(body.severity or "medium") if manager else "medium",
        category=body.category,
        source="manual" if manager else "employee_report",
        actor=ctx.user,
        owner_id=owner,
        asset_ids=body.asset_ids,
        alerts=alerts,
    )
    audit.record(
        db,
        "incident.created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="incident",
        resource_id=incident.id,
        details={"reference": incident.reference, "source": incident.source},
        request=ctx.request,
    )
    db.commit()
    _send(mails)
    return _incident_out(db, incident)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail, tags=["Incidents"])
def get_incident(
    incident_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
) -> IncidentDetail:
    inc = _load_incident(db, ctx, incident_id)
    assets = db.scalars(
        select(Asset)
        .join(IncidentAsset, IncidentAsset.asset_id == Asset.id)
        .where(IncidentAsset.incident_id == inc.id)
        .order_by(Asset.name)
    )
    alerts = db.execute(
        select(Alert, Asset.name)
        .join(IncidentAlert, IncidentAlert.alert_id == Alert.id)
        .join(Asset, Asset.id == Alert.asset_id)
        .where(IncidentAlert.incident_id == inc.id)
        .order_by(Alert.first_seen_at.desc())
    ).all()
    timeline = db.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == inc.id)
        .order_by(IncidentEvent.occurred_at.desc())
    )
    evidence = db.scalars(
        select(IncidentEvidence)
        .where(IncidentEvidence.incident_id == inc.id)
        .order_by(IncidentEvidence.created_at.desc())
    )
    tasks = db.scalars(
        select(RemediationTask)
        .where(RemediationTask.incident_id == inc.id)
        .order_by(RemediationTask.created_at)
    )
    now = datetime.now(UTC)
    return IncidentDetail(
        **_incident_out(db, inc).model_dump(),
        assets=[
            IncidentAssetOut(
                id=a.id,
                name=a.name,
                identifier=a.identifier,
                type=a.type,
                criticality=a.criticality,
            )
            for a in assets
        ],
        alerts=[
            IncidentAlertOut(
                id=a.id,
                title=a.title,
                severity=a.severity,
                status=a.status,
                asset_name=n,
                first_seen_at=a.first_seen_at,
            )
            for a, n in alerts
        ],
        timeline=[TimelineEntry.model_validate(t) for t in timeline],
        evidence=[
            EvidenceOut.model_validate(e).model_copy(
                update={"uploaded_by_name": p.name if (p := _person(db, e.uploaded_by)) else None}
            )
            for e in evidence
        ],
        tasks=[_task_out(db, t, now) for t in tasks],
        can_manage=ctx.has(Perm.INCIDENTS_MANAGE),
    )


@router.patch("/incidents/{incident_id}", response_model=IncidentOut, tags=["Incidents"])
def update_incident(
    incident_id: uuid.UUID,
    body: IncidentUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> IncidentOut:
    inc = _load_incident(db, ctx, incident_id)
    now = datetime.now(UTC)
    mails = []
    if body.title is not None and body.title.strip() and body.title.strip() != inc.title:
        inc.title = body.title.strip()
    if body.summary is not None:
        inc.summary = body.summary.strip()
    if body.category and body.category != inc.category:
        service.add_event(
            db,
            inc,
            "category_changed",
            actor=ctx.user,
            body=f"Category set to {body.category.replace('_', ' ')}.",
        )
        inc.category = body.category
    if body.severity and body.severity != inc.severity:
        service.add_event(
            db,
            inc,
            "severity_changed",
            actor=ctx.user,
            body=f"Severity changed from {inc.severity} to {body.severity}.",
            data={"from": inc.severity, "to": body.severity},
        )
        inc.severity = body.severity
    if body.clear_owner and inc.owner_id:
        inc.owner_id = None
        service.add_event(db, inc, "assigned", actor=ctx.user, body="Owner removed.")
    elif body.owner_id and body.owner_id != inc.owner_id:
        owner = _member(db, ctx, body.owner_id)
        inc.owner_id = owner.id
        service.add_event(
            db,
            inc,
            "assigned",
            actor=ctx.user,
            body=f"Assigned to {owner.full_name or owner.email}.",
        )
        if owner.id != ctx.user.id:
            mails += service.notify(
                db,
                inc,
                f"You've been assigned {inc.reference}: {inc.title}",
                inc.summary or "An incident has been assigned to you.",
                users=[owner],
            )
    if body.status and body.status != inc.status:
        if body.status == "closed" and not body.closure_reason:
            raise APIError(
                422,
                "validation_error",
                "Choose a closure reason.",
                [{"field": "closure_reason", "message": "Required to close."}],
            )
        previous = inc.status
        reopened = previous in ("resolved", "closed") and body.status in service.OPEN_STATUSES
        inc.status = body.status
        if body.status == "contained":
            inc.contained_at = inc.contained_at or now
        if body.status in ("resolved", "closed"):
            inc.resolved_at = inc.resolved_at or now
        if body.status == "closed":
            inc.closed_at = now
            inc.closure_reason = body.closure_reason
        if body.resolution_summary is not None:
            inc.resolution_summary = body.resolution_summary.strip() or None
        if reopened:
            inc.closed_at = inc.resolved_at = None
            inc.closure_reason = None
        service.add_event(
            db,
            inc,
            "reopened" if reopened else ("closed" if body.status == "closed" else "status_changed"),
            actor=ctx.user,
            body={
                "investigating": "Investigation started.",
                "contained": "Marked as contained.",
                "resolved": "Marked as resolved.",
                "closed": f"Closed: {(body.closure_reason or '').replace('_', ' ')}.",
                "open": "Reopened.",
            }.get(body.status, f"Status: {body.status}")
            + (f" {body.resolution_summary.strip()}" if body.resolution_summary else ""),
            data={"from": previous, "to": body.status},
        )
    audit.record(
        db,
        "incident.updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="incident",
        resource_id=inc.id,
        details={"reference": inc.reference, "fields": sorted(body.model_dump(exclude_unset=True))},
        request=ctx.request,
    )
    db.commit()
    _send(mails)
    return _incident_out(db, inc)


@router.post(
    "/incidents/{incident_id}/notes",
    response_model=TimelineEntry,
    status_code=201,
    tags=["Incidents"],
)
def add_note(
    incident_id: uuid.UUID,
    body: NoteCreate,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
) -> TimelineEntry:
    inc = _load_incident(db, ctx, incident_id)
    event = service.add_event(db, inc, "note", actor=ctx.user, body=body.body)
    db.commit()
    return TimelineEntry.model_validate(event)


@router.post("/incidents/{incident_id}/assets", response_model=IncidentOut, tags=["Incidents"])
def add_asset(
    incident_id: uuid.UUID,
    body: LinkAsset,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> IncidentOut:
    inc = _load_incident(db, ctx, incident_id)
    asset = db.get(Asset, body.asset_id)
    if asset is None or asset.organisation_id != ctx.org_id:
        raise not_found("Asset")
    service.link_asset(db, inc, asset.id, ctx.user)
    db.commit()
    return _incident_out(db, inc)


@router.post("/incidents/{incident_id}/alerts", response_model=IncidentOut, tags=["Incidents"])
def add_alert(
    incident_id: uuid.UUID,
    body: LinkAlert,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> IncidentOut:
    inc = _load_incident(db, ctx, incident_id)
    alert = db.get(Alert, body.alert_id)
    if alert is None or alert.organisation_id != ctx.org_id:
        raise not_found("Alert")
    service.link_alert(db, inc, alert, ctx.user)
    db.commit()
    return _incident_out(db, inc)


def _safe_filename(name: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]).strip(" .")
    return (base or "evidence")[:200]


@router.post(
    "/incidents/{incident_id}/evidence",
    response_model=EvidenceOut,
    status_code=201,
    tags=["Incidents"],
)
async def upload_evidence(
    incident_id: uuid.UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=500),
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
) -> EvidenceOut:
    inc = _load_incident(db, ctx, incident_id)
    filename = _safe_filename(file.filename or "evidence")
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in EVIDENCE_EXTENSIONS:
        raise APIError(
            415,
            "unsupported_file",
            "Upload screenshots, PDFs, text logs, emails, packet captures or zip files.",
        )
    data = await file.read(settings.max_evidence_bytes + 1)
    if len(data) > settings.max_evidence_bytes:
        raise APIError(413, "payload_too_large", "Evidence files can be up to 10 MB.")
    if not data:
        raise APIError(422, "validation_error", "The file is empty.")
    digest = hashlib.sha256(data).hexdigest()
    key = storage.put(ctx.org_id, "evidence", data)
    evidence = IncidentEvidence(
        organisation_id=ctx.org_id,
        incident_id=inc.id,
        filename=filename,
        content_type=(file.content_type or "application/octet-stream")[:100],
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        description=(description or "").strip() or None,
        uploaded_by=ctx.user.id,
    )
    db.add(evidence)
    db.flush()
    service.add_event(
        db,
        inc,
        "evidence_added",
        actor=ctx.user,
        body=f"Evidence added: {filename}",
        data={"evidence_id": str(evidence.id), "sha256": digest, "size_bytes": len(data)},
    )
    audit.record(
        db,
        "incident.evidence_added",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="incident",
        resource_id=inc.id,
        details={"filename": filename, "sha256": digest},
        request=ctx.request,
    )
    db.commit()
    return EvidenceOut.model_validate(evidence).model_copy(
        update={"uploaded_by_name": ctx.user.full_name or ctx.user.email}
    )


@router.get("/incidents/{incident_id}/evidence/{evidence_id}", tags=["Incidents"])
def download_evidence(
    incident_id: uuid.UUID,
    evidence_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.INCIDENTS_REPORT)),
    db: Session = Depends(get_db),
) -> Response:
    inc = _load_incident(db, ctx, incident_id)
    evidence = db.get(IncidentEvidence, evidence_id)
    if evidence is None or evidence.incident_id != inc.id:
        raise not_found("Evidence")
    data = storage.get(ctx.org_id, evidence.storage_key)
    if hashlib.sha256(data).hexdigest() != evidence.sha256:
        raise APIError(500, "integrity_error", "This file failed its integrity check.")
    audit.record(
        db,
        "incident.evidence_downloaded",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="incident",
        resource_id=inc.id,
        details={"filename": evidence.filename},
        request=ctx.request,
    )
    db.commit()
    # Always a download, never rendered in the browser: evidence may be hostile content.
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{evidence.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


# --- Remediation tasks ---------------------------------------------------------------------


def _load_task(db: Session, ctx: OrgContext, task_id: uuid.UUID) -> RemediationTask:
    task = db.get(RemediationTask, task_id)
    if task is None or task.organisation_id != ctx.org_id:
        raise not_found("Task")
    if not ctx.has(Perm.REMEDIATION_READ) and task.assignee_id != ctx.user.id:
        raise not_found("Task")
    return task


@router.get("/remediation-tasks", response_model=Page[TaskOut], tags=["Remediation"])
def list_tasks(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)),
    db: Session = Depends(get_db),
    status: list[str] | None = Query(default=None),
    mine: bool = False,
    overdue: bool = False,
    finding_id: uuid.UUID | None = None,
    incident_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[TaskOut]:
    now = datetime.now(UTC)
    stmt = select(RemediationTask).where(RemediationTask.organisation_id == ctx.org_id)
    if mine or not ctx.has(Perm.REMEDIATION_READ):
        stmt = stmt.where(RemediationTask.assignee_id == ctx.user.id)
    stmt = stmt.where(RemediationTask.status.in_(status or ["open", "in_progress", "done"]))
    if overdue:
        stmt = stmt.where(
            RemediationTask.due_at < now, RemediationTask.status.in_(("open", "in_progress"))
        )
    if finding_id:
        stmt = stmt.where(RemediationTask.finding_id == finding_id)
    if incident_id:
        stmt = stmt.where(RemediationTask.incident_id == incident_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(RemediationTask.due_at.asc().nulls_last(), RemediationTask.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[TaskOut](
        items=[_task_out(db, t, now) for t in rows], total=total, page=page, page_size=page_size
    )


@router.post("/remediation-tasks", response_model=TaskOut, status_code=201, tags=["Remediation"])
def create_task(
    body: TaskCreate,
    ctx: OrgContext = Depends(org_scope(Perm.REMEDIATION_MANAGE)),
    db: Session = Depends(get_db),
) -> TaskOut:
    finding = incident = None
    if body.finding_id:
        finding = db.get(Finding, body.finding_id)
        if finding is None or finding.organisation_id != ctx.org_id:
            raise not_found("Finding")
    if body.incident_id:
        incident = _load_incident(db, ctx, body.incident_id)
    if not finding and not (body.title and body.title.strip()):
        raise APIError(
            422,
            "validation_error",
            "Give the task a title.",
            [{"field": "title", "message": "Required."}],
        )
    priority = body.priority or (
        ("low" if finding.severity == "informational" else finding.severity)
        if finding
        else (incident.severity if incident else "medium")
    )
    assignee = _member(db, ctx, body.assignee_id) if body.assignee_id else None
    task = RemediationTask(
        organisation_id=ctx.org_id,
        finding_id=finding.id if finding else None,
        incident_id=incident.id if incident else None,
        asset_id=finding.asset_id if finding else None,
        kind=body.kind,
        title=(body.title or "").strip() or f"Fix: {finding.title}",
        description=(body.description or "").strip() or (finding.recommendation if finding else ""),
        priority=priority,
        assignee_id=assignee.id if assignee else None,
        created_by=ctx.user.id,
        due_at=body.due_at or service.default_due(priority),
    )
    db.add(task)
    db.flush()
    mails = []
    if incident:
        service.add_event(
            db,
            incident,
            "task_added",
            actor=ctx.user,
            body=f"{task.kind.capitalize()} action added: {task.title}"
            + (f" (assigned to {assignee.full_name or assignee.email})" if assignee else ""),
            data={"task_id": str(task.id)},
        )
    if assignee and assignee.id != ctx.user.id:
        mails = _task_notice(db, ctx, task, assignee)
    audit.record(
        db,
        "remediation.task_created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="remediation_task",
        resource_id=task.id,
        details={"title": task.title, "finding": str(task.finding_id or "")},
        request=ctx.request,
    )
    db.commit()
    _send(mails)
    return _task_out(db, task)


def _task_notice(db: Session, ctx: OrgContext, task: RemediationTask, assignee: User) -> list:
    """Tell someone a task is theirs: in the app always, by email for urgent work."""
    with system_context(db):
        db.add(
            Notification(
                organisation_id=ctx.org_id,
                user_id=assignee.id,
                severity=task.priority,
                title=f"Task assigned: {task.title}"[:200],
                body=(task.description or "")[:1000],
                link="/remediation?mine=1",
            )
        )
        db.flush()
    if task.priority in ("critical", "high"):
        return [
            EmailJob(
                assignee.email,
                f"Security task assigned to you: {task.title}",
                f"{task.description}\n\nDue: {task.due_at:%d %b %Y}\n\n"
                f"View your tasks: {settings.web_base_url}/remediation?mine=1",
            )
        ]
    return []


@router.patch("/remediation-tasks/{task_id}", response_model=TaskOut, tags=["Remediation"])
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = _load_task(db, ctx, task_id)
    manager = ctx.has(Perm.REMEDIATION_MANAGE)
    changes = body.model_dump(exclude_unset=True)
    if not manager:
        # Assignees can report progress on their own tasks, nothing more.
        if (
            task.assignee_id != ctx.user.id
            or set(changes) - {"status", "note"}
            or (body.status and body.status not in ("in_progress", "done"))
        ):
            raise forbidden("You can only update the progress of tasks assigned to you.")
    now = datetime.now(UTC)
    mails = []
    if body.title:
        task.title = body.title.strip()
    if body.description is not None:
        task.description = body.description.strip()
    if body.priority:
        task.priority = body.priority
    if "due_at" in changes:
        task.due_at = body.due_at
    if body.note is not None:
        task.note = body.note.strip() or None
    if body.clear_assignee:
        task.assignee_id = None
    elif body.assignee_id and body.assignee_id != task.assignee_id:
        assignee = _member(db, ctx, body.assignee_id)
        task.assignee_id = assignee.id
        if assignee.id != ctx.user.id:
            mails = _task_notice(db, ctx, task, assignee)
    if body.status and body.status != task.status:
        previous = task.status
        task.status = body.status
        if body.status == "done":
            task.completed_at = now
            finding = db.get(Finding, task.finding_id) if task.finding_id else None
            if finding is not None and finding.status != "open":
                task.status, task.verified_at = "verified", now
                task.verification = "monitoring" if finding.resolved_by is None else "manual"
        elif body.status == "verified":
            if not manager:
                raise forbidden()
            task.verified_at, task.verification = now, "manual"
            task.completed_at = task.completed_at or now
        elif body.status in ("open", "in_progress"):
            task.completed_at = task.verified_at = task.verification = None
        if task.incident_id:
            incident = db.get(Incident, task.incident_id)
            service.add_event(
                db,
                incident,
                "task_updated",
                actor=ctx.user,
                body=f"Task '{task.title}': {previous.replace('_', ' ')} → "
                f"{task.status.replace('_', ' ')}",
                data={"task_id": str(task.id), "status": task.status},
            )
    audit.record(
        db,
        "remediation.task_updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="remediation_task",
        resource_id=task.id,
        details={"fields": sorted(changes), "status": task.status},
        request=ctx.request,
    )
    db.commit()
    _send(mails)
    return _task_out(db, task)


@router.get("/remediation/summary", response_model=RemediationSummary, tags=["Remediation"])
def remediation_summary(
    ctx: OrgContext = Depends(org_scope(Perm.REMEDIATION_READ)), db: Session = Depends(get_db)
) -> RemediationSummary:
    now = datetime.now(UTC)
    base = select(RemediationTask).where(RemediationTask.organisation_id == ctx.org_id)

    def count(*conds) -> int:
        return db.scalar(select(func.count()).select_from(base.where(*conds).subquery())) or 0

    finished = list(
        db.scalars(
            base.where(
                RemediationTask.status == "verified",
                RemediationTask.completed_at >= now - timedelta(days=30),
            )
        )
    )
    with_due = [t for t in finished if t.due_at]
    on_time = (
        round(100 * sum(1 for t in with_due if t.completed_at <= t.due_at) / len(with_due))
        if with_due
        else None
    )
    days = [(t.completed_at - t.created_at).total_seconds() / 86400 for t in finished]
    has_task = (
        select(RemediationTask.id)
        .where(
            RemediationTask.finding_id == Finding.id,
            RemediationTask.status.in_(("open", "in_progress", "done")),
        )
        .exists()
    )
    unassigned = (
        db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.organisation_id == ctx.org_id,
                Finding.status == "open",
                Finding.severity.in_(("critical", "high")),
                ~has_task,
            )
        )
        or 0
    )
    return RemediationSummary(
        open=count(RemediationTask.status == "open"),
        in_progress=count(RemediationTask.status == "in_progress"),
        awaiting_verification=count(RemediationTask.status == "done"),
        overdue=count(
            RemediationTask.status.in_(("open", "in_progress")), RemediationTask.due_at < now
        ),
        completed_30d=len(finished),
        on_time_rate=on_time,
        median_days_to_fix=round(statistics.median(days), 1) if days else None,
        unassigned_urgent_findings=unassigned,
    )
