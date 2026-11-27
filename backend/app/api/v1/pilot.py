"""Pilot programme tools: muting known conditions, product feedback and pilot measurements."""

import statistics
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, OrgContext, get_auth, org_scope, require_platform_admin
from app.billing.service import effective_status
from app.core.db import get_db, system_context
from app.core.errors import APIError, not_found
from app.core.redis import rate_limit
from app.models import (
    Agent,
    Alert,
    Asset,
    AuthSession,
    Feedback,
    Membership,
    Organisation,
    Subscription,
    SuppressionRule,
    User,
)
from app.monitoring.catalogue import RULES
from app.security.rbac import Perm
from app.services import audit

router = APIRouter()

# --- Suppression (muted alerts) ---------------------------------------------------------------


class SuppressionCreate(BaseModel):
    alert_id: uuid.UUID | None = None
    rule_key: str | None = Field(default=None, max_length=64)
    asset_id: uuid.UUID | None = None
    all_assets: bool = False
    reason: str = Field(min_length=3, max_length=500)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class SuppressionOut(BaseModel):
    id: uuid.UUID
    rule_key: str
    rule_title: str
    asset_id: uuid.UUID | None
    asset_name: str | None
    reason: str
    expires_at: datetime | None
    hits: int
    last_hit_at: datetime | None
    created_by_name: str | None
    created_at: datetime


def _suppression_out(db: Session, r: SuppressionRule) -> SuppressionOut:
    asset = db.get(Asset, r.asset_id) if r.asset_id else None
    creator = db.get(User, r.created_by) if r.created_by else None
    rule = RULES.get(r.rule_key)
    return SuppressionOut(
        id=r.id,
        rule_key=r.rule_key,
        rule_title=rule.title if rule else r.rule_key,
        asset_id=r.asset_id,
        asset_name=asset.name if asset else None,
        reason=r.reason,
        expires_at=r.expires_at,
        hits=r.hits,
        last_hit_at=r.last_hit_at,
        created_by_name=(creator.full_name or creator.email) if creator else None,
        created_at=r.created_at,
    )


@router.get("/suppression-rules", response_model=list[SuppressionOut], tags=["Alerts"])
def list_suppressions(
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_READ)), db: Session = Depends(get_db)
) -> list[SuppressionOut]:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(SuppressionRule)
        .where(
            SuppressionRule.organisation_id == ctx.org_id,
            SuppressionRule.removed_at.is_(None),
            (SuppressionRule.expires_at.is_(None)) | (SuppressionRule.expires_at > now),
        )
        .order_by(SuppressionRule.created_at.desc())
    )
    return [_suppression_out(db, r) for r in rows]


@router.post("/suppression-rules", response_model=SuppressionOut, status_code=201, tags=["Alerts"])
def create_suppression(
    body: SuppressionCreate,
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_MANAGE)),
    db: Session = Depends(get_db),
) -> SuppressionOut:
    """Mute one kind of alert, on one asset or all of them. Findings are still recorded."""
    rule_key, asset_id = body.rule_key, body.asset_id
    alert = None
    if body.alert_id:
        alert = db.get(Alert, body.alert_id)
        if alert is None or alert.organisation_id != ctx.org_id:
            raise not_found("Alert")
        from app.models import Finding

        finding = db.get(Finding, alert.finding_id)
        rule_key, asset_id = finding.rule_key, alert.asset_id
    if not rule_key or rule_key not in RULES:
        raise APIError(422, "validation_error", "Choose the kind of alert to mute.")
    if RULES[rule_key].severity == "critical":
        raise APIError(
            422,
            "cannot_mute_critical",
            "Critical alerts can't be muted. Accept the risk on the finding instead, with a "
            "reason.",
        )
    if body.all_assets:
        asset_id = None
    elif asset_id is not None:
        asset = db.get(Asset, asset_id)
        if asset is None or asset.organisation_id != ctx.org_id:
            raise APIError(422, "validation_error", "Choose an asset from this organisation.")
    now = datetime.now(UTC)
    rule = SuppressionRule(
        organisation_id=ctx.org_id,
        rule_key=rule_key,
        asset_id=asset_id,
        reason=body.reason.strip(),
        expires_at=now + timedelta(days=body.expires_in_days) if body.expires_in_days else None,
        created_by=ctx.user.id,
    )
    db.add(rule)
    if alert is not None and alert.status != "resolved":
        alert.status, alert.resolved_at, alert.resolved_by = "resolved", now, ctx.user.id
        alert.outcome = "expected"
        alert.resolution_note = f"Muted: {rule.reason}"
    db.flush()
    audit.record(
        db,
        "alert.muted",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="suppression_rule",
        resource_id=rule.id,
        details={
            "rule": rule_key,
            "asset_id": str(asset_id) if asset_id else "all",
            "reason": rule.reason,
            "days": body.expires_in_days,
        },
        request=ctx.request,
    )
    db.commit()
    return _suppression_out(db, rule)


@router.delete("/suppression-rules/{rule_id}", status_code=204, tags=["Alerts"])
def remove_suppression(
    rule_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ALERTS_MANAGE)),
    db: Session = Depends(get_db),
) -> None:
    rule = db.get(SuppressionRule, rule_id)
    if rule is None or rule.organisation_id != ctx.org_id or rule.removed_at:
        raise not_found("Muting rule")
    rule.removed_at = datetime.now(UTC)
    audit.record(
        db,
        "alert.unmuted",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="suppression_rule",
        resource_id=rule.id,
        details={"rule": rule.rule_key},
        request=ctx.request,
    )
    db.commit()


# --- Product feedback -------------------------------------------------------------------------


class FeedbackCreate(BaseModel):
    kind: Literal["idea", "problem", "praise", "question"]
    message: str = Field(min_length=3, max_length=5000)
    page: str | None = Field(default=None, max_length=200)
    rating: int | None = Field(default=None, ge=1, le=5)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    kind: str
    message: str
    page: str | None
    rating: int | None
    status: str
    organisation_name: str | None
    user_name: str | None
    created_at: datetime


@router.post("/feedback", status_code=201, tags=["Feedback"])
def send_feedback(
    body: FeedbackCreate,
    request: Request,
    x_organisation_id: str | None = Header(default=None),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    rate_limit(f"feedback:{auth.user.id}", limit=20, window_seconds=3600)
    org_id = None
    if x_organisation_id:
        try:
            candidate = uuid.UUID(x_organisation_id)
        except ValueError:
            candidate = None
        if candidate and db.scalar(
            select(Membership.id).where(
                Membership.organisation_id == candidate,
                Membership.user_id == auth.user.id,
                Membership.status == "active",
            )
        ):
            org_id = candidate
    db.add(
        Feedback(
            organisation_id=org_id,
            user_id=auth.user.id,
            kind=body.kind,
            message=body.message.strip(),
            page=body.page,
            rating=body.rating,
        )
    )
    db.commit()
    return {"message": "Thank you. The team reads every message."}


@router.get("/platform/feedback", response_model=list[FeedbackOut], tags=["Platform"])
def list_feedback(
    status: str | None = Query(default=None, max_length=16),
    _: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[FeedbackOut]:
    with system_context(db):
        stmt = (
            select(Feedback, Organisation.name, User.full_name)
            .outerjoin(Organisation, Organisation.id == Feedback.organisation_id)
            .outerjoin(User, User.id == Feedback.user_id)
            .order_by(Feedback.created_at.desc())
            .limit(200)
        )
        if status:
            stmt = stmt.where(Feedback.status == status)
        rows = db.execute(stmt).all()
    return [
        FeedbackOut(
            id=f.id,
            kind=f.kind,
            message=f.message,
            page=f.page,
            rating=f.rating,
            status=f.status,
            organisation_name=org,
            user_name=name,
            created_at=f.created_at,
        )
        for f, org, name in rows
    ]


class FeedbackStatus(BaseModel):
    status: Literal["new", "reviewed", "done"]


@router.patch("/platform/feedback/{feedback_id}", tags=["Platform"])
def update_feedback(
    feedback_id: uuid.UUID,
    body: FeedbackStatus,
    _: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> dict:
    with system_context(db):
        f = db.get(Feedback, feedback_id)
        if f is None:
            raise not_found("Feedback")
        f.status = body.status
        db.commit()
    return {"status": body.status}


# --- Pilot measurements -----------------------------------------------------------------------


class PilotOrg(BaseModel):
    organisation_id: uuid.UUID
    name: str
    plan: str
    subscription: str
    paying: bool
    assets: int
    assets_monitored_pct: int | None
    agents_enrolled: int
    agents_reporting_pct: int | None
    alerts_30d: int
    false_positive_pct: int | None
    median_minutes_to_acknowledge: float | None
    median_hours_to_resolve: float | None
    active_users_7d: int
    members: int
    feedback_count: int


class PilotMetrics(BaseModel):
    organisations: list[PilotOrg]
    generated_at: datetime


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


@router.get("/platform/pilot-metrics", response_model=PilotMetrics, tags=["Platform"])
def pilot_metrics(
    _: AuthContext = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> PilotMetrics:
    """The pilot measurements from the product plan, per organisation. Counts and timings only."""
    now = datetime.now(UTC)
    since = now - timedelta(days=30)
    out = []
    with system_context(db):
        orgs = db.scalars(
            select(Organisation)
            .where(Organisation.deleted_at.is_(None))
            .order_by(Organisation.created_at)
        ).all()
        for org in orgs:
            assets = db.scalars(
                select(Asset).where(Asset.organisation_id == org.id, Asset.status == "active")
            ).all()
            monitored = sum(1 for a in assets if a.last_successful_check_at or a.last_seen_at)
            agents = db.scalars(
                select(Agent).where(
                    Agent.organisation_id == org.id,
                    Agent.status == "active",
                    Agent.source != "collector",
                )
            ).all()
            reporting = sum(
                1 for a in agents if a.last_seen_at and a.last_seen_at > now - timedelta(hours=1)
            )
            alerts = db.scalars(
                select(Alert).where(Alert.organisation_id == org.id, Alert.first_seen_at >= since)
            ).all()
            judged = [a for a in alerts if a.outcome in {"fixed", "false_positive", "expected"}]
            fp = sum(1 for a in judged if a.outcome == "false_positive")
            ack = [
                (a.acknowledged_at - a.first_seen_at).total_seconds() / 60
                for a in alerts
                if a.acknowledged_at
            ]
            resolve = [
                (a.resolved_at - a.first_seen_at).total_seconds() / 3600
                for a in alerts
                if a.resolved_at and a.outcome != "cleared"
            ]
            member_ids = db.scalars(
                select(Membership.user_id).where(
                    Membership.organisation_id == org.id, Membership.status == "active"
                )
            ).all()
            active = (
                db.scalar(
                    select(func.count(func.distinct(AuthSession.user_id))).where(
                        AuthSession.user_id.in_(member_ids),
                        AuthSession.last_used_at > now - timedelta(days=7),
                    )
                )
                if member_ids
                else 0
            ) or 0
            sub = db.scalar(select(Subscription).where(Subscription.organisation_id == org.id))
            status = effective_status(sub) if sub else "none"
            feedback = (
                db.scalar(select(func.count()).where(Feedback.organisation_id == org.id)) or 0
            )
            out.append(
                PilotOrg(
                    organisation_id=org.id,
                    name=org.name,
                    plan=sub.plan_code if sub else "none",
                    subscription=status,
                    paying=status in {"active", "past_due"},
                    assets=len(assets),
                    assets_monitored_pct=round(100 * monitored / len(assets)) if assets else None,
                    agents_enrolled=len(agents),
                    agents_reporting_pct=round(100 * reporting / len(agents)) if agents else None,
                    alerts_30d=len(alerts),
                    false_positive_pct=round(100 * fp / len(judged)) if judged else None,
                    median_minutes_to_acknowledge=_median(ack),
                    median_hours_to_resolve=_median(resolve),
                    active_users_7d=active,
                    members=len(member_ids),
                    feedback_count=feedback,
                )
            )
    return PilotMetrics(organisations=out, generated_at=now)
