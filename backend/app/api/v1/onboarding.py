"""Getting started: the steps from a new workspace to a monitored business (Journey A)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.billing.service import effective_status
from app.core.db import get_db
from app.models import Agent, Asset, Invitation, Membership, PushDevice, Subscription
from app.security.rbac import Perm
from app.services import audit

router = APIRouter(tags=["Onboarding"])

VERIFIED = ("authorised", "monitoring", "degraded")


class Step(BaseModel):
    id: str
    title: str
    description: str
    done: bool
    optional: bool = False
    href: str | None = None
    action_label: str | None = None


class Onboarding(BaseModel):
    steps: list[Step]
    completed: int
    required: int
    required_done: int
    complete: bool
    dismissed: bool


def _any(db: Session, stmt) -> bool:
    return bool(db.scalar(select(exists(stmt))))


def build(db: Session, ctx: OrgContext) -> Onboarding:
    org = ctx.organisation
    org_assets = select(Asset.id).where(Asset.organisation_id == org.id, Asset.status == "active")
    members = (
        db.scalar(
            select(func.count()).where(
                Membership.organisation_id == org.id, Membership.status == "active"
            )
        )
        or 0
    )
    sub = db.scalar(select(Subscription).where(Subscription.organisation_id == org.id))
    steps = [
        Step(
            id="profile",
            title="Complete your business profile",
            description="Industry and a contact number help us tailor findings and reach you.",
            done=bool(org.industry and org.phone),
            href="/settings",
            action_label="Edit profile",
        ),
        Step(
            id="asset",
            title="Add your website or domain",
            description="Start with what customers see: your website, domain or email domain.",
            done=_any(db, org_assets),
            href="/assets?new=1",
            action_label="Add asset",
        ),
        Step(
            id="verify",
            title="Prove you control it",
            description="Add a DNS record or upload a file. We only monitor what you're "
            "allowed to.",
            done=_any(db, org_assets.where(Asset.monitoring_status.in_(VERIFIED))),
            href="/assets",
            action_label="Verify",
        ),
        Step(
            id="monitoring",
            title="See your first results",
            description="Checks start straight after verification. Results usually arrive "
            "in minutes.",
            done=_any(db, org_assets.where(Asset.last_successful_check_at.is_not(None))),
            href="/monitoring",
            action_label="View monitoring",
        ),
        Step(
            id="team",
            title="Invite your IT person or team",
            description="Give each person a role so they see only what they need.",
            done=members > 1
            or _any(db, select(Invitation.id).where(Invitation.organisation_id == org.id)),
            href="/team",
            action_label="Invite",
        ),
        Step(
            id="mfa",
            title="Turn on two-step sign-in",
            description="Protect your own account with an authenticator app.",
            done=ctx.user.mfa_enabled,
            href="/settings/security",
            action_label="Set up",
        ),
        Step(
            id="endpoint",
            title="Install the agent on your computers",
            description="See device health, protection and suspicious sign-ins.",
            done=_any(
                db,
                select(Agent.id).where(
                    Agent.organisation_id == org.id, Agent.source == "smecm_agent"
                ),
            ),
            optional=True,
            href="/endpoints",
            action_label="Add a device",
        ),
        Step(
            id="mobile",
            title="Get alerts on your phone",
            description="Install the mobile app and allow notifications to hear about urgent "
            "problems straight away.",
            done=_any(db, select(PushDevice.id).where(PushDevice.user_id == ctx.user.id)),
            optional=True,
        ),
    ]
    if ctx.has(Perm.BILLING_READ):
        steps.append(
            Step(
                id="plan",
                title="Choose a plan",
                description="Pay monthly or yearly with Mobile Money or card. No contract.",
                done=sub is not None and effective_status(sub) in {"active", "past_due"},
                optional=True,
                href="/settings/subscription",
                action_label="See plans",
            )
        )
    required = [s for s in steps if not s.optional]
    required_done = sum(1 for s in required if s.done)
    return Onboarding(
        steps=steps,
        completed=sum(1 for s in steps if s.done),
        required=len(required),
        required_done=required_done,
        complete=required_done == len(required),
        dismissed=org.onboarding_dismissed_at is not None,
    )


@router.get("/onboarding", response_model=Onboarding)
def get_onboarding(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_READ)), db: Session = Depends(get_db)
) -> Onboarding:
    return build(db, ctx)


class DismissRequest(BaseModel):
    dismissed: bool = True


@router.put("/onboarding/dismissed", response_model=Onboarding)
def set_dismissed(
    body: DismissRequest,
    request: Request,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> Onboarding:
    """Hide (or bring back) the getting-started checklist for the whole organisation."""
    ctx.organisation.onboarding_dismissed_at = datetime.now(UTC) if body.dismissed else None
    audit.record(
        db,
        "organisation.onboarding_dismissed" if body.dismissed else "organisation.onboarding_shown",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="organisation",
        resource_id=ctx.org_id,
        request=request,
    )
    db.commit()
    return build(db, ctx)
