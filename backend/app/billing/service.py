"""Subscriptions, checkout and the subscription lifecycle.

Billing is prepaid: each successful payment buys one period (30 days, or 365 for annual
billing). Mobile Money cannot be charged automatically, so instead of silent renewals owners get
reminders 7, 3 and 1 day(s) before a period ends, and a grace period after it.

    trialing ──pay──▶ active ──period ends──▶ past_due ──grace ends──▶ expired
        └──────────── trial ends ─────────────────────────────────────▶ expired

An expired organisation keeps its data and its existing monitoring (switching off security
monitoring abruptly would put the customer at risk), but cannot add assets, members, agents or
collectors until it pays.
"""

import logging
import math
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import set_tenant_context
from app.core.errors import APIError
from app.models import Agent, Asset, Membership, Organisation, Payment, Subscription, User
from app.security.rbac import Role
from app.services.email import send_email
from app.services.plans import PLANS, Plan, get_plan

log = logging.getLogger("app.billing")

PERIOD_DAYS = {"monthly": 30, "annual": 365}
REMINDER_DAYS = (7, 3, 1)
LAPSED = {"expired", "cancelled"}


def price_minor(plan: Plan, period: str) -> int | None:
    """Price in pesewas for one period, or None for custom (Enterprise) pricing."""
    if plan.monthly_price_ghs is None:
        return None
    months = settings.annual_months_charged if period == "annual" else 1
    return plan.monthly_price_ghs * months * 100


def get_subscription(db: Session, org_id: uuid.UUID, *, lock: bool = False) -> Subscription:
    stmt = select(Subscription).where(Subscription.organisation_id == org_id)
    if lock:
        stmt = stmt.with_for_update()
    sub = db.scalar(stmt)
    if sub is None:
        raise APIError(404, "not_found", "No subscription found.")
    return sub


def effective_status(sub: Subscription, now: datetime | None = None) -> str:
    """The status as of ``now``, even if the hourly sweep has not caught up yet."""
    now = now or datetime.now(UTC)
    end = sub.current_period_end
    if sub.status in LAPSED or end is None:
        return sub.status
    if now <= end:
        return sub.status
    if sub.status == "trialing":
        return "expired"
    if now <= end + timedelta(days=settings.billing_grace_days):
        return "past_due"
    return "expired"


def ensure_can_grow(db: Session, org_id: uuid.UUID) -> None:
    """Block adding assets, people, agents and collectors while the subscription is lapsed."""
    sub = db.scalar(select(Subscription).where(Subscription.organisation_id == org_id))
    if sub is not None and effective_status(sub) in LAPSED:
        raise APIError(
            402,
            "subscription_lapsed",
            "Your subscription has ended. Renew it in Settings → Subscription to add more.",
        )


@dataclass
class Usage:
    assets: int
    members: int
    collectors: int


def usage(db: Session, org_id: uuid.UUID) -> Usage:
    assets = db.scalar(
        select(func.count()).where(Asset.organisation_id == org_id, Asset.status == "active")
    )
    members = db.scalar(
        select(func.count()).where(
            Membership.organisation_id == org_id, Membership.status == "active"
        )
    )
    collectors = db.scalar(
        select(func.count()).where(
            Agent.organisation_id == org_id, Agent.source == "collector", Agent.status == "active"
        )
    )
    return Usage(assets or 0, members or 0, collectors or 0)


def plan_blockers(plan: Plan, used: Usage) -> list[str]:
    """Reasons the organisation's current usage does not fit a plan (for downgrades)."""
    out = []
    if plan.asset_limit is not None and used.assets > plan.asset_limit:
        out.append(f"{used.assets} active assets (the plan includes {plan.asset_limit})")
    if plan.member_limit is not None and used.members > plan.member_limit:
        out.append(f"{used.members} team members (the plan includes {plan.member_limit})")
    if plan.collector_limit is not None and used.collectors > plan.collector_limit:
        out.append(
            f"{used.collectors} network collectors (the plan includes {plan.collector_limit})"
        )
    return out


def credit_days(sub: Subscription, plan: Plan, period: str, now: datetime) -> int:
    """Unused paid time on the current plan, converted into days on the new plan."""
    if sub.status not in {"active", "past_due"} or not sub.current_period_end:
        return 0
    remaining = (sub.current_period_end - now).total_seconds() / 86400
    if remaining <= 0:
        return 0
    old_price = price_minor(get_plan(sub.plan_code), sub.billing_period)
    new_price = price_minor(plan, period)
    if not old_price or not new_price:
        return 0
    value = remaining / PERIOD_DAYS.get(sub.billing_period, 30) * old_price
    return math.floor(value / (new_price / PERIOD_DAYS[period]))


def new_reference() -> str:
    return f"smecm_{secrets.token_hex(12)}"


def start_checkout(
    db: Session,
    org: Organisation,
    user: User,
    plan_code: str,
    period: str,
    channel: str,
) -> Payment:
    if plan_code not in PLANS:
        raise APIError(422, "unknown_plan", "Choose one of the listed plans.")
    plan = get_plan(plan_code)
    amount = price_minor(plan, period)
    if amount is None:
        raise APIError(
            400,
            "contact_sales",
            f"{plan.name} pricing is agreed with our team. Email {settings.billing_contact_email}.",
        )
    blockers = plan_blockers(plan, usage(db, org.id))
    if blockers:
        raise APIError(
            409,
            "plan_too_small",
            f"The {plan.name} plan does not fit your current usage: "
            + "; ".join(blockers)
            + ". Remove some first, or choose a bigger plan.",
        )
    payment = Payment(
        organisation_id=org.id,
        reference=new_reference(),
        provider=settings.payment_provider,
        plan_code=plan.code,
        billing_period=period,
        amount_minor=amount,
        currency="GHS",
        channel=channel,
        status="pending",
        created_by=user.id,
    )
    db.add(payment)
    db.flush()
    return payment


def apply_success(
    db: Session,
    payment: Payment,
    *,
    amount_minor: int | None,
    currency: str | None,
    provider_reference: str | None = None,
    payment_method: dict | None = None,
    now: datetime | None = None,
) -> bool:
    """Activate the subscription for a confirmed payment. Safe to call more than once.

    Returns True when this call applied the payment. Callers hold the RLS context for the
    payment's organisation (or the system context, for webhooks).
    """
    now = now or datetime.now(UTC)
    sub = get_subscription(db, payment.organisation_id, lock=True)
    db.refresh(payment, with_for_update=True)
    if payment.status == "success":
        return False
    if amount_minor != payment.amount_minor or (currency or "").upper() != payment.currency:
        # Never activate on a payment that does not match what we asked for.
        payment.status = "failed"
        payment.failure_reason = "Amount or currency did not match the order."
        log.warning(
            "payment %s amount mismatch: got %s %s", payment.reference, amount_minor, currency
        )
        return False

    plan = get_plan(payment.plan_code)
    period_days = PERIOD_DAYS[payment.billing_period]
    status = effective_status(sub, now)
    same_terms = sub.plan_code == plan.code and sub.billing_period == payment.billing_period
    end = sub.current_period_end
    if same_terms and status == "active" and end and end > now:
        # Early renewal: the new period starts when the current one ends.
        start, credit = sub.current_period_end, 0
    else:
        start = now
        credit = 0 if same_terms else credit_days(sub, plan, payment.billing_period, now)

    receipt = (
        db.scalar(
            select(func.max(Payment.receipt_number)).where(
                Payment.organisation_id == payment.organisation_id
            )
        )
        or 0
    ) + 1
    payment.status = "success"
    payment.paid_at = now
    payment.failure_reason = None
    payment.provider_reference = provider_reference or payment.provider_reference
    payment.payment_method = payment_method or {}
    payment.receipt_number = receipt
    payment.credit_days = credit
    payment.period_start = start
    payment.period_end = start + timedelta(days=period_days + credit)

    sub.plan_code = plan.code
    sub.billing_period = payment.billing_period
    sub.status = "active"
    sub.current_period_end = payment.period_end
    sub.last_reminder = None
    return True


def apply_failure(payment: Payment, status: str, reason: str | None) -> None:
    if payment.status == "pending":
        payment.status = status if status in {"failed", "abandoned"} else "failed"
        payment.failure_reason = (reason or "")[:300] or None


def receipt_label(payment: Payment) -> str:
    return f"SMECM-{payment.paid_at:%Y}-{payment.receipt_number:05d}" if payment.paid_at else ""


# --- Lifecycle sweep (monitor worker, hourly) ---------------------------------------------


def _billing_contacts(db: Session, org_id: uuid.UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organisation_id == org_id,
                Membership.status == "active",
                Membership.role.in_([Role.OWNER, Role.ADMIN]),
                User.status == "active",
            )
        )
    )


def _mail(db: Session, org: Organisation, subject: str, body: str) -> int:
    link = f"{settings.web_base_url}/settings/subscription"
    contacts = _billing_contacts(db, org.id)
    for user in contacts:
        send_email(
            user.email,
            subject,
            f"{body}\n\nManage your subscription: {link}\n\n"
            f"{settings.brand_product_name} · Powered by {settings.brand_company_name}",
        )
    return len(contacts)


def sweep_subscriptions(db: Session, now: datetime | None = None) -> int:
    """Move subscriptions through their lifecycle and send reminders. Runs in system context."""
    now = now or datetime.now(UTC)
    sent = 0
    rows = db.execute(
        select(Subscription, Organisation)
        .join(Organisation, Organisation.id == Subscription.organisation_id)
        .where(Organisation.status == "active", Subscription.status.notin_(LAPSED))
    ).all()
    for sub, org in rows:
        set_tenant_context(db, org=org.id)
        end = sub.current_period_end
        if end is None:
            continue
        plan = get_plan(sub.plan_code)
        new_status = effective_status(sub, now)
        if new_status != sub.status:
            previous, sub.status = sub.status, new_status
            if new_status == "past_due":
                grace = end + timedelta(days=settings.billing_grace_days)
                sent += _mail(
                    db,
                    org,
                    f"Payment due: {org.name}'s {plan.name} plan",
                    f"Your {plan.name} plan for {org.name} ended on {end:%d %B %Y}. Monitoring "
                    f"continues until {grace:%d %B %Y}. Renew with Mobile Money or card before "
                    "then to avoid interruption.",
                )
            elif new_status == "expired":
                what = "free trial" if previous == "trialing" else f"{plan.name} plan"
                sent += _mail(
                    db,
                    org,
                    f"{org.name}'s {what} has ended",
                    f"The {what} for {org.name} has ended. Your data and existing monitoring "
                    "are kept, but you can't add assets, team members, agents or collectors "
                    "until you choose a plan.",
                )
            continue
        days_left = (end - now).total_seconds() / 86400
        # The nearest reminder threshold we have reached (1, 3 or 7 days before the end).
        threshold = next((d for d in sorted(REMINDER_DAYS) if days_left <= d), None)
        if threshold is None:
            continue
        prefix = f"{end.isoformat()}:"
        last = sub.last_reminder
        if last and last.startswith(prefix) and int(last.rsplit(":", 1)[1]) <= threshold:
            continue  # this reminder (or a nearer one) already went out for this period
        sub.last_reminder = f"{prefix}{threshold}"
        what = "free trial" if sub.status == "trialing" else f"{plan.name} plan"
        day_word = "day" if threshold == 1 else "days"
        sent += _mail(
            db,
            org,
            f"{org.name}'s {what} ends in {threshold} {day_word}",
            f"The {what} for {org.name} ends on {end:%d %B %Y}. Pay with Mobile Money "
            "or card to keep monitoring without interruption.",
        )
    db.commit()
    return sent
