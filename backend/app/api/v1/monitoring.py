import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.core.db import get_db
from app.core.errors import APIError, not_found
from app.core.redis import rate_limit
from app.incidents.service import cancel_tasks_for_finding, verify_tasks_for_finding
from app.models import (
    Alert,
    Asset,
    CheckRun,
    Finding,
    Incident,
    IncidentAlert,
    MonitoringCheck,
    Notification,
    NotificationPreference,
    User,
)
from app.monitoring.catalogue import RULES
from app.monitoring.engine import ALLOWED_INTERVALS, DEFAULT_CHECKS, RUNNABLE_ASSET_STATES
from app.monitoring.scoring import compute_posture
from app.schemas.common import Page
from app.schemas.monitoring import (
    AlertDetail,
    AlertOut,
    AlertUpdate,
    AssetRef,
    CheckCreate,
    CheckOut,
    CheckUpdate,
    FindingDetail,
    FindingOut,
    FindingUpdate,
    MarkRead,
    MonitoringSummary,
    NotificationList,
    NotificationOut,
    NotificationPreferences,
    RunOut,
)
from app.security.rbac import Perm
from app.services import audit

router = APIRouter(tags=["Monitoring"])

SEVERITY_SORT = case(
    {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4},
    value=Finding.severity,
)
ALERT_SEVERITY_SORT = case(
    {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4},
    value=Alert.severity,
)


def _asset_ref(asset: Asset | None) -> AssetRef | None:
    if asset is None:
        return None
    return AssetRef(
        id=asset.id,
        name=asset.name,
        identifier=asset.identifier,
        type=asset.type,
        criticality=asset.criticality,
    )


def _user_name(db: Session, user_id) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return (user.full_name or user.email) if user else None


# --- Checks -------------------------------------------------------------------------------


@router.get("/monitoring/summary", response_model=MonitoringSummary)
def monitoring_summary(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)), db: Session = Depends(get_db)
) -> MonitoringSummary:
    active = Asset.status == "active"
    rows = db.execute(
        select(MonitoringCheck.enabled, MonitoringCheck.last_status, func.count())
        .join(Asset, Asset.id == MonitoringCheck.asset_id)
        .where(MonitoringCheck.organisation_id == ctx.org_id, active)
        .group_by(MonitoringCheck.enabled, MonitoringCheck.last_status)
    ).all()
    by_status: dict[str, int] = {}
    total = enabled = 0
    for is_enabled, status, n in rows:
        total += n
        if is_enabled:
            enabled += n
            by_status[status] = by_status.get(status, 0) + n
        else:
            by_status["disabled"] = by_status.get("disabled", 0) + n
    posture = compute_posture(db, ctx.org_id)
    awaiting = (
        db.scalar(
            select(func.count()).where(
                Asset.organisation_id == ctx.org_id,
                active,
                Asset.type.in_(list(DEFAULT_CHECKS)),
                Asset.monitoring_status == "not_monitored",
            )
        )
        or 0
    )
    return MonitoringSummary(
        checks_total=total,
        checks_enabled=enabled,
        by_status=by_status,
        monitored_assets=posture["monitored_assets"],
        monitorable_assets=posture["monitorable_assets"],
        awaiting_authorisation=awaiting,
        assets_with_check_errors=posture["assets_with_check_errors"],
    )


@router.get("/monitoring/checks", response_model=list[CheckOut])
def list_checks(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)),
    db: Session = Depends(get_db),
    asset_id: uuid.UUID | None = None,
    check_type: str | None = None,
    status: str | None = None,
) -> list[CheckOut]:
    stmt = (
        select(MonitoringCheck, Asset)
        .join(Asset, Asset.id == MonitoringCheck.asset_id)
        .where(MonitoringCheck.organisation_id == ctx.org_id, Asset.status == "active")
    )
    if asset_id:
        stmt = stmt.where(MonitoringCheck.asset_id == asset_id)
    if check_type:
        stmt = stmt.where(MonitoringCheck.check_type == check_type)
    if status == "disabled":
        stmt = stmt.where(MonitoringCheck.enabled.is_(False))
    elif status:
        stmt = stmt.where(MonitoringCheck.last_status == status, MonitoringCheck.enabled.is_(True))
    rows = db.execute(stmt.order_by(Asset.name, MonitoringCheck.check_type).limit(500)).all()
    return [CheckOut.model_validate(c).model_copy(update={"asset": _asset_ref(a)}) for c, a in rows]


def _load_check(db: Session, ctx: OrgContext, check_id: uuid.UUID) -> MonitoringCheck:
    check = db.get(MonitoringCheck, check_id)
    if check is None or check.organisation_id != ctx.org_id:
        raise not_found("Check")
    return check


@router.post("/monitoring/checks", response_model=CheckOut, status_code=201)
def create_check(
    body: CheckCreate,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> CheckOut:
    asset = db.get(Asset, body.asset_id)
    if asset is None or asset.organisation_id != ctx.org_id:
        raise not_found("Asset")
    allowed = dict(DEFAULT_CHECKS.get(asset.type, []))
    if body.check_type not in allowed:
        raise APIError(
            422, "check_not_supported", "That check isn't available for this type of asset."
        )
    if db.scalar(
        select(MonitoringCheck.id).where(
            MonitoringCheck.asset_id == asset.id, MonitoringCheck.check_type == body.check_type
        )
    ):
        raise APIError(409, "check_exists", "This check already exists for the asset.")
    check = MonitoringCheck(
        organisation_id=ctx.org_id,
        asset_id=asset.id,
        check_type=body.check_type,
        interval_minutes=allowed[body.check_type],
        next_run_at=datetime.now(UTC),
    )
    db.add(check)
    db.flush()
    audit.record(
        db,
        "monitoring.check_created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=asset.id,
        details={"check_type": body.check_type},
        request=ctx.request,
    )
    db.commit()
    return CheckOut.model_validate(check).model_copy(update={"asset": _asset_ref(asset)})


@router.patch("/monitoring/checks/{check_id}", response_model=CheckOut)
def update_check(
    check_id: uuid.UUID,
    body: CheckUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> CheckOut:
    check = _load_check(db, ctx, check_id)
    changes = {}
    if body.interval_minutes is not None and body.interval_minutes != check.interval_minutes:
        if body.interval_minutes not in ALLOWED_INTERVALS:
            raise APIError(
                422,
                "validation_error",
                "Choose one of the listed intervals.",
                [{"field": "interval_minutes", "message": "Unsupported interval."}],
            )
        changes["interval_minutes"] = {"from": check.interval_minutes, "to": body.interval_minutes}
        check.interval_minutes = body.interval_minutes
    if body.enabled is not None and body.enabled != check.enabled:
        changes["enabled"] = body.enabled
        check.enabled = body.enabled
        if body.enabled:
            check.next_run_at = datetime.now(UTC)
    if changes:
        audit.record(
            db,
            "monitoring.check_updated",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="asset",
            resource_id=check.asset_id,
            details={"check_type": check.check_type, **changes},
            request=ctx.request,
        )
        db.commit()
    asset = db.get(Asset, check.asset_id)
    return CheckOut.model_validate(check).model_copy(update={"asset": _asset_ref(asset)})


@router.post("/monitoring/checks/{check_id}/run", response_model=CheckOut)
def run_check_now(
    check_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> CheckOut:
    check = _load_check(db, ctx, check_id)
    rate_limit(f"run-check:{check.id}", limit=6, window_seconds=300)
    asset = db.get(Asset, check.asset_id)
    if asset.monitoring_status not in RUNNABLE_ASSET_STATES or asset.status != "active":
        raise APIError(409, "asset_not_authorised", "Authorise this asset before running checks.")
    if not check.enabled:
        raise APIError(409, "check_disabled", "Turn this check on first.")
    check.next_run_at = datetime.now(UTC)
    db.commit()
    return CheckOut.model_validate(check).model_copy(update={"asset": _asset_ref(asset)})


@router.get("/monitoring/runs", response_model=Page[RunOut])
def list_runs(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)),
    db: Session = Depends(get_db),
    asset_id: uuid.UUID | None = None,
    check_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[RunOut]:
    stmt = select(CheckRun).where(CheckRun.organisation_id == ctx.org_id)
    if asset_id:
        stmt = stmt.where(CheckRun.asset_id == asset_id)
    if check_id:
        stmt = stmt.where(CheckRun.check_id == check_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(CheckRun.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[RunOut](
        items=[RunOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )


# --- Findings -----------------------------------------------------------------------------


@router.get("/findings", response_model=Page[FindingOut])
def list_findings(
    ctx: OrgContext = Depends(org_scope(Perm.FINDINGS_READ)),
    db: Session = Depends(get_db),
    severity: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    asset_id: uuid.UUID | None = None,
    check_type: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[FindingOut]:
    stmt = (
        select(Finding, Asset)
        .join(Asset, Asset.id == Finding.asset_id)
        .where(Finding.organisation_id == ctx.org_id, Asset.status == "active")
    )
    stmt = stmt.where(Finding.status.in_(status or ["open"]))
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if asset_id:
        stmt = stmt.where(Finding.asset_id == asset_id)
    if check_type:
        stmt = stmt.where(Finding.check_type == check_type)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Finding.title.ilike(like), Asset.name.ilike(like), Asset.identifier.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(SEVERITY_SORT, Finding.last_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[FindingOut](
        items=[
            FindingOut.model_validate(f).model_copy(update={"asset": _asset_ref(a)})
            for f, a in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _load_finding(db: Session, ctx: OrgContext, finding_id: uuid.UUID) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None or finding.organisation_id != ctx.org_id:
        raise not_found("Finding")
    return finding


def _finding_detail(db: Session, finding: Finding) -> FindingDetail:
    alert_id = db.scalar(
        select(Alert.id).where(Alert.finding_id == finding.id, Alert.status != "resolved")
    )
    rule = RULES.get(finding.rule_key)
    return FindingDetail.model_validate(finding).model_copy(
        update={
            "asset": _asset_ref(db.get(Asset, finding.asset_id)),
            "open_alert_id": alert_id,
            "sticky": bool(rule and rule.sticky),
            "resolved_by_name": _user_name(db, finding.resolved_by),
        }
    )


@router.get("/findings/{finding_id}", response_model=FindingDetail)
def get_finding(
    finding_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.FINDINGS_READ)),
    db: Session = Depends(get_db),
) -> FindingDetail:
    return _finding_detail(db, _load_finding(db, ctx, finding_id))


@router.patch("/findings/{finding_id}", response_model=FindingDetail)
def update_finding(
    finding_id: uuid.UUID,
    body: FindingUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.FINDINGS_MANAGE)),
    db: Session = Depends(get_db),
) -> FindingDetail:
    finding = _load_finding(db, ctx, finding_id)
    if body.status == "accepted_risk" and not (body.note and body.note.strip()):
        raise APIError(
            422,
            "validation_error",
            "Explain why this risk is accepted.",
            [{"field": "note", "message": "Required when accepting a risk."}],
        )
    previous = finding.status
    now = datetime.now(UTC)
    finding.status = body.status
    note = (body.note or "").strip() or None
    if body.status == "open":
        finding.resolved_at = finding.resolved_by = finding.resolution_note = None
    else:
        finding.resolved_at, finding.resolved_by, finding.resolution_note = now, ctx.user.id, note
        # The person has dealt with it, so close the alert too.
        db.execute(
            update(Alert)
            .where(Alert.finding_id == finding.id, Alert.status != "resolved")
            .values(
                status="resolved",
                resolved_at=now,
                resolved_by=ctx.user.id,
                resolution_note=note or f"Finding marked {body.status.replace('_', ' ')}",
            )
        )
    if body.status == "resolved":
        verify_tasks_for_finding(db, finding, "manual", ctx.user)
    elif body.status == "accepted_risk":
        cancel_tasks_for_finding(db, finding, "Risk accepted")
    audit.record(
        db,
        "finding.updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=finding.asset_id,
        details={"finding": finding.title, "from": previous, "to": body.status, "note": note},
        request=ctx.request,
    )
    db.commit()
    return _finding_detail(db, finding)


# --- Alerts -------------------------------------------------------------------------------


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_READ)),
    db: Session = Depends(get_db),
    severity: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    asset_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[AlertOut]:
    stmt = (
        select(Alert, Asset)
        .join(Asset, Asset.id == Alert.asset_id)
        .where(Alert.organisation_id == ctx.org_id)
    )
    stmt = stmt.where(Alert.status.in_(status or ["new", "acknowledged", "investigating"]))
    if severity:
        stmt = stmt.where(Alert.severity.in_(severity))
    if asset_id:
        stmt = stmt.where(Alert.asset_id == asset_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(ALERT_SEVERITY_SORT, Alert.last_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[AlertOut](
        items=[
            AlertOut.model_validate(a).model_copy(update={"asset": _asset_ref(s)}) for a, s in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _incident_ref(db: Session, alert: Alert) -> dict | None:
    incident = db.scalar(
        select(Incident)
        .join(IncidentAlert, IncidentAlert.incident_id == Incident.id)
        .where(IncidentAlert.alert_id == alert.id)
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    if incident is None:
        return None
    return {
        "id": incident.id,
        "reference": incident.reference,
        "title": incident.title,
        "status": incident.status,
    }


def _alert_detail(db: Session, alert: Alert) -> AlertDetail:
    finding = db.get(Finding, alert.finding_id)
    asset = db.get(Asset, alert.asset_id)
    return AlertDetail.model_validate(
        {
            **AlertOut.model_validate(alert).model_dump(),
            "asset": _asset_ref(asset),
            "finding": FindingOut.model_validate(finding).model_copy(
                update={"asset": _asset_ref(asset)}
            ),
            "acknowledged_by_name": _user_name(db, alert.acknowledged_by),
            "resolved_by_name": _user_name(db, alert.resolved_by),
            "incident": _incident_ref(db, alert),
        }
    )


def _load_alert(db: Session, ctx: OrgContext, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.organisation_id != ctx.org_id:
        raise not_found("Alert")
    return alert


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_READ)),
    db: Session = Depends(get_db),
) -> AlertDetail:
    return _alert_detail(db, _load_alert(db, ctx, alert_id))


@router.patch("/alerts/{alert_id}", response_model=AlertDetail)
def update_alert(
    alert_id: uuid.UUID,
    body: AlertUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_MANAGE)),
    db: Session = Depends(get_db),
) -> AlertDetail:
    alert = _load_alert(db, ctx, alert_id)
    if alert.status == "resolved" and body.status != "resolved":
        raise APIError(
            409,
            "alert_resolved",
            "This alert is closed. A new alert opens if the problem comes back.",
        )
    now = datetime.now(UTC)
    previous = alert.status
    alert.status = body.status
    if body.status in {"acknowledged", "investigating"} and alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by = now, ctx.user.id
    if body.status == "resolved" and previous != "resolved":
        alert.resolved_at, alert.resolved_by = now, ctx.user.id
        alert.resolution_note = (body.note or "").strip() or None
    audit.record(
        db,
        "alert.updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=alert.asset_id,
        details={
            "alert": alert.title,
            "from": previous,
            "to": body.status,
            "note": (body.note or "").strip() or None,
        },
        request=ctx.request,
    )
    db.commit()
    return _alert_detail(db, alert)


# --- Notifications ------------------------------------------------------------------------


@router.get("/notifications", response_model=NotificationList)
def list_notifications(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)),
    db: Session = Depends(get_db),
    unread_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
) -> NotificationList:
    base = select(Notification).where(
        Notification.organisation_id == ctx.org_id, Notification.user_id == ctx.user.id
    )
    unread = (
        db.scalar(
            select(func.count()).select_from(base.where(Notification.read_at.is_(None)).subquery())
        )
        or 0
    )
    stmt = base.where(Notification.read_at.is_(None)) if unread_only else base
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit))
    return NotificationList(items=[NotificationOut.model_validate(n) for n in rows], unread=unread)


@router.post("/notifications/read", response_model=NotificationList)
def mark_read(
    body: MarkRead,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)),
    db: Session = Depends(get_db),
) -> NotificationList:
    stmt = update(Notification).where(
        Notification.organisation_id == ctx.org_id,
        Notification.user_id == ctx.user.id,
        Notification.read_at.is_(None),
    )
    if body.ids:
        stmt = stmt.where(Notification.id.in_(body.ids))
    db.execute(stmt.values(read_at=datetime.now(UTC)))
    db.commit()
    return list_notifications(ctx, db, unread_only=False, limit=20)


def _prefs(db: Session, ctx: OrgContext) -> NotificationPreference | None:
    return db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.organisation_id == ctx.org_id,
            NotificationPreference.user_id == ctx.user.id,
        )
    )


@router.get("/notifications/preferences", response_model=NotificationPreferences)
def get_preferences(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)), db: Session = Depends(get_db)
) -> NotificationPreferences:
    pref = _prefs(db, ctx)
    if pref is None:
        return NotificationPreferences()
    return NotificationPreferences(
        email_min_severity=pref.email_min_severity, in_app_min_severity=pref.in_app_min_severity
    )


@router.put("/notifications/preferences", response_model=NotificationPreferences)
def set_preferences(
    body: NotificationPreferences,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)),
    db: Session = Depends(get_db),
) -> NotificationPreferences:
    pref = _prefs(db, ctx)
    if pref is None:
        pref = NotificationPreference(organisation_id=ctx.org_id, user_id=ctx.user.id)
        db.add(pref)
    pref.email_min_severity = body.email_min_severity
    pref.in_app_min_severity = body.in_app_min_severity
    db.commit()
    return body
