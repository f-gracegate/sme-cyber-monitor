"""Organisation-wide views: overview, audit log, billing and the platform console."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, OrgContext, org_scope, require_platform_admin
from app.core.config import settings
from app.core.db import get_db, system_context
from app.core.errors import APIError
from app.models import (
    Alert,
    Asset,
    AuditLog,
    Finding,
    Invitation,
    Membership,
    Organisation,
    RiskScoreSnapshot,
    Subscription,
    User,
)
from app.models.asset import ASSET_CATEGORIES
from app.monitoring.catalogue import severity_rank
from app.monitoring.scoring import compute_posture
from app.schemas.asset import AuditEntryOut
from app.schemas.common import Page
from app.security.rbac import Perm, Role
from app.services.email import read_dev_mailbox
from app.services.plans import PLANS, get_plan

router = APIRouter(tags=["Workspace"])

PRIVILEGED_ROLES = {Role.OWNER, Role.ADMIN, Role.IT_ADMIN}


class Recommendation(BaseModel):
    id: str
    severity: str
    title: str
    description: str
    action_label: str
    action_href: str


class Overview(BaseModel):
    organisation_name: str
    assets_total: int
    assets_by_category: dict[str, int]
    assets_by_monitoring_status: dict[str, int]
    assets_authorised: int
    critical_assets: int
    members_total: int
    members_with_mfa: int
    privileged_without_mfa: int
    pending_invitations: int
    posture_score: int | None
    posture_note: str
    recommendations: list[Recommendation]
    monitored_assets: int
    monitorable_assets: int
    assets_with_check_errors: int
    findings_open_by_severity: dict[str, int]
    findings_by_status: dict[str, int]
    alerts_open_by_severity: dict[str, int]
    recent_alerts: list["AlertBrief"]
    most_exposed_assets: list["ExposedAsset"]
    trend: list["TrendPoint"]


class AlertBrief(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    status: str
    asset_name: str
    last_seen_at: datetime


class ExposedAsset(BaseModel):
    id: uuid.UUID
    name: str
    identifier: str
    type: str
    open_findings: int
    highest_severity: str


class TrendPoint(BaseModel):
    day: str
    score: int


Overview.model_rebuild()


@router.get("/overview", response_model=Overview)
def overview(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)), db: Session = Depends(get_db)
) -> Overview:
    org_id = ctx.org_id
    by_type = dict(
        db.execute(
            select(Asset.type, func.count())
            .where(Asset.organisation_id == org_id, Asset.status == "active")
            .group_by(Asset.type)
        ).all()
    )
    by_category: dict[str, int] = {c: 0 for c in sorted(set(ASSET_CATEGORIES.values()))}
    for t, n in by_type.items():
        by_category[ASSET_CATEGORIES.get(t, "other")] = (
            by_category.get(ASSET_CATEGORIES.get(t, "other"), 0) + n
        )
    by_status = dict(
        db.execute(
            select(Asset.monitoring_status, func.count())
            .where(Asset.organisation_id == org_id, Asset.status == "active")
            .group_by(Asset.monitoring_status)
        ).all()
    )
    critical = (
        db.scalar(
            select(func.count()).where(
                Asset.organisation_id == org_id,
                Asset.status == "active",
                Asset.criticality == "critical",
            )
        )
        or 0
    )
    members = db.execute(
        select(Membership.role, User.mfa_enabled)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organisation_id == org_id, Membership.status == "active")
    ).all()
    pending = (
        db.scalar(
            select(func.count()).where(
                Invitation.organisation_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
        )
        or 0
    )

    total_assets = sum(by_type.values())
    authorised = total_assets - by_status.get("not_monitored", 0)
    with_mfa = sum(1 for _, mfa in members if mfa)
    privileged_without = sum(1 for role, mfa in members if role in PRIVILEGED_ROLES and not mfa)

    recs: list[Recommendation] = []
    if not ctx.user.mfa_enabled:
        recs.append(
            Recommendation(
                id="self_mfa",
                severity="critical",
                title="Turn on multi-factor authentication",
                description="Your account is protected by a password only. Add an "
                "authenticator app so a stolen password is not enough to get in.",
                action_label="Set up MFA",
                action_href="/settings/security",
            )
        )
    if privileged_without and ctx.has(Perm.MEMBERS_MANAGE):
        recs.append(
            Recommendation(
                id="admins_mfa",
                severity="critical",
                title=f"{privileged_without} administrator account(s) without MFA",
                description="Privileged accounts are the most valuable to attackers. Require MFA "
                "for everyone in your organisation.",
                action_label="Review team",
                action_href="/team",
            )
        )
    if total_assets == 0 and ctx.has(Perm.ASSETS_WRITE):
        recs.append(
            Recommendation(
                id="first_asset",
                severity="high",
                title="Register your first asset",
                description="Start with your website or domain, then add computers and servers.",
                action_label="Add asset",
                action_href="/assets?new=1",
            )
        )
    unverified = by_status.get("not_monitored", 0)
    if unverified and ctx.has(Perm.ASSETS_VERIFY):
        recs.append(
            Recommendation(
                id="verify_assets",
                severity="medium",
                title=f"{unverified} asset(s) waiting for authorisation",
                description="We only monitor assets you have proven you own or are allowed to "
                "monitor.",
                action_label="Review assets",
                action_href="/assets?monitoring_status=not_monitored",
            )
        )
    if not ctx.organisation.require_mfa and ctx.has(Perm.ORG_UPDATE):
        recs.append(
            Recommendation(
                id="require_mfa",
                severity="medium",
                title="Require MFA for your whole team",
                description="Make multi-factor authentication mandatory for every member.",
                action_label="Open settings",
                action_href="/settings/security",
            )
        )
    if len(members) <= 1 and ctx.has(Perm.MEMBERS_MANAGE):
        recs.append(
            Recommendation(
                id="invite_team",
                severity="low",
                title="Invite your IT staff",
                description="Share the work: invite the people who look after your computers and "
                "website.",
                action_label="Invite people",
                action_href="/team",
            )
        )

    posture = compute_posture(db, org_id)
    open_sev = posture["open_by_severity"]
    active_asset = (Asset.organisation_id == org_id) & (Asset.status == "active")
    findings_by_status = dict(
        db.execute(
            select(Finding.status, func.count())
            .join(Asset, Asset.id == Finding.asset_id)
            .where(Finding.organisation_id == org_id, active_asset)
            .group_by(Finding.status)
        ).all()
    )
    alerts_sev = dict(
        db.execute(
            select(Alert.severity, func.count())
            .where(Alert.organisation_id == org_id, Alert.status != "resolved")
            .group_by(Alert.severity)
        ).all()
    )
    recent_alerts = []
    if ctx.has(Perm.ALERTS_READ):
        recent_alerts = [
            AlertBrief(
                id=a.id,
                title=a.title,
                severity=a.severity,
                status=a.status,
                asset_name=name,
                last_seen_at=a.last_seen_at,
            )
            for a, name in db.execute(
                select(Alert, Asset.name)
                .join(Asset, Asset.id == Alert.asset_id)
                .where(Alert.organisation_id == org_id, Alert.status != "resolved")
                .order_by(Alert.last_seen_at.desc())
                .limit(5)
            ).all()
        ]
    exposed: dict[uuid.UUID, ExposedAsset] = {}
    if ctx.has(Perm.FINDINGS_READ):
        for asset, sev in db.execute(
            select(Asset, Finding.severity)
            .join(Finding, Finding.asset_id == Asset.id)
            .where(active_asset, Finding.status == "open", Finding.severity != "informational")
        ).all():
            entry = exposed.setdefault(
                asset.id,
                ExposedAsset(
                    id=asset.id,
                    name=asset.name,
                    identifier=asset.identifier,
                    type=asset.type,
                    open_findings=0,
                    highest_severity=sev,
                ),
            )
            entry.open_findings += 1
            if severity_rank(sev) > severity_rank(entry.highest_severity):
                entry.highest_severity = sev
    most_exposed = sorted(
        exposed.values(),
        key=lambda e: (severity_rank(e.highest_severity), e.open_findings),
        reverse=True,
    )[:5]
    since = datetime.now(UTC).date() - timedelta(days=30)
    trend = [
        TrendPoint(day=snap.day.isoformat(), score=snap.score)
        for snap in db.scalars(
            select(RiskScoreSnapshot)
            .where(RiskScoreSnapshot.organisation_id == org_id, RiskScoreSnapshot.day >= since)
            .order_by(RiskScoreSnapshot.day)
        )
    ]

    urgent = open_sev["critical"] + open_sev["high"]
    if urgent and ctx.has(Perm.FINDINGS_READ):
        recs.append(
            Recommendation(
                id="urgent_findings",
                severity="critical" if open_sev["critical"] else "high",
                title=f"Fix {urgent} urgent security finding(s)",
                description="Critical and high findings are the issues most likely to be exploited "
                "or to take your services offline.",
                action_label="View findings",
                action_href="/findings?severity=critical&severity=high",
            )
        )
    if posture["assets_with_check_errors"] and ctx.has(Perm.MONITORING_READ):
        n = posture["assets_with_check_errors"]
        recs.append(
            Recommendation(
                id="check_errors",
                severity="medium",
                title=f"{n} asset(s) couldn't be checked",
                description="Some checks failed to run, so we can't see these assets clearly. "
                "Missing data never improves your score.",
                action_label="Open monitoring",
                action_href="/monitoring?status=error",
            )
        )
    recs.sort(key=lambda r: severity_rank(r.severity), reverse=True)

    if posture["score"] is None:
        note = (
            "A security score needs monitoring data. It appears once an authorised website or "
            "domain has been checked, and is never raised by missing data."
        )
    else:
        note = (
            f"Based on {posture['monitored_assets']} monitored asset(s). Each open finding "
            "lowers the score by its severity; assets we can't check are shown as coverage "
            "gaps, not as good news."
        )

    return Overview(
        monitored_assets=posture["monitored_assets"],
        monitorable_assets=posture["monitorable_assets"],
        assets_with_check_errors=posture["assets_with_check_errors"],
        findings_open_by_severity=open_sev,
        findings_by_status={
            k: findings_by_status.get(k, 0) for k in ("open", "accepted_risk", "resolved")
        },
        alerts_open_by_severity={k: alerts_sev.get(k, 0) for k in open_sev},
        recent_alerts=recent_alerts,
        most_exposed_assets=most_exposed,
        trend=trend,
        organisation_name=ctx.organisation.name,
        assets_total=total_assets,
        assets_by_category=by_category,
        assets_by_monitoring_status=by_status,
        assets_authorised=authorised,
        critical_assets=critical,
        members_total=len(members),
        members_with_mfa=with_mfa,
        privileged_without_mfa=privileged_without,
        pending_invitations=pending,
        posture_score=posture["score"],
        posture_note=note,
        recommendations=recs,
    )


@router.get("/audit-logs", response_model=Page[AuditEntryOut])
def audit_logs(
    ctx: OrgContext = Depends(org_scope(Perm.AUDIT_READ)),
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=80),
    actor: str | None = Query(default=None, max_length=320),
    resource_type: str | None = Query(default=None, max_length=40),
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AuditEntryOut]:
    stmt = select(AuditLog).where(AuditLog.organisation_id == ctx.org_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if actor:
        stmt = stmt.where(AuditLog.actor_label.ilike(f"%{actor}%"))
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[AuditEntryOut](
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


class PlanOut(BaseModel):
    code: str
    name: str
    monthly_price_ghs: int | None
    asset_limit: int | None
    member_limit: int | None
    features: list[str]


class SubscriptionOut(BaseModel):
    plan: PlanOut
    status: str
    billing_period: str
    current_period_end: datetime | None
    assets_used: int
    members_used: int
    available_plans: list[PlanOut]


def _plan_out(code: str) -> PlanOut:
    p = get_plan(code)
    return PlanOut(
        code=p.code,
        name=p.name,
        monthly_price_ghs=p.monthly_price_ghs,
        asset_limit=p.asset_limit,
        member_limit=p.member_limit,
        features=list(p.features),
    )


@router.get("/billing/subscription", response_model=SubscriptionOut)
def subscription(
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_READ)), db: Session = Depends(get_db)
) -> SubscriptionOut:
    sub = db.scalar(select(Subscription).where(Subscription.organisation_id == ctx.org_id))
    if sub is None:
        raise APIError(404, "not_found", "No subscription found.")
    assets = (
        db.scalar(
            select(func.count()).where(
                Asset.organisation_id == ctx.org_id, Asset.status == "active"
            )
        )
        or 0
    )
    members = db.scalar(select(func.count()).where(Membership.organisation_id == ctx.org_id)) or 0
    return SubscriptionOut(
        plan=_plan_out(sub.plan_code),
        status=sub.status,
        billing_period=sub.billing_period,
        current_period_end=sub.current_period_end,
        assets_used=assets,
        members_used=members,
        available_plans=[_plan_out(c) for c in PLANS],
    )


class PlatformOrganisation(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    status: str
    plan_code: str | None
    members: int
    assets: int
    created_at: datetime


@router.get("/platform/organisations", response_model=list[PlatformOrganisation])
def platform_organisations(
    auth: AuthContext = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[PlatformOrganisation]:
    """Customer list for the platform operations team. Shows counts only, never tenant data."""
    members = (
        select(func.count()).where(Membership.organisation_id == Organisation.id).scalar_subquery()
    )
    assets = (
        select(func.count())
        .where(Asset.organisation_id == Organisation.id, Asset.status == "active")
        .scalar_subquery()
    )
    with system_context(db):
        rows = db.execute(
            select(Organisation, Subscription.plan_code, members, assets)
            .outerjoin(Subscription, Subscription.organisation_id == Organisation.id)
            .order_by(Organisation.created_at.desc())
        ).all()
    return [
        PlatformOrganisation(
            id=o.id,
            name=o.name,
            industry=o.industry,
            status=o.status,
            plan_code=plan,
            members=m,
            assets=a,
            created_at=o.created_at,
        )
        for o, plan, m, a in rows
    ]


@router.get("/dev/mailbox", include_in_schema=False)
def dev_mailbox() -> list[dict]:
    """Development only: recent emails, so invitations and resets can be tested locally."""
    if not settings.is_development:
        raise APIError(404, "not_found", "Not found.")
    return read_dev_mailbox()
