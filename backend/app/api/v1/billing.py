"""Subscriptions and payments (Mobile Money and card, through Paystack)."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.billing import service
from app.billing.providers import PaystackProvider, ProviderError, get_provider
from app.billing.receipt import render_receipt
from app.core.config import settings
from app.core.db import get_db, set_tenant_context, system_context
from app.core.errors import APIError
from app.core.redis import rate_limit
from app.models import Payment
from app.schemas.common import Page
from app.security.rbac import Perm
from app.services import audit
from app.services.plans import PLANS, get_plan

log = logging.getLogger("app.billing")
router = APIRouter(tags=["Billing"])

Period = Literal["monthly", "annual"]
Channel = Literal["mobile_money", "card"]


class PlanOut(BaseModel):
    code: str
    name: str
    monthly_price_ghs: int | None
    annual_price_ghs: int | None
    asset_limit: int | None
    member_limit: int | None
    collector_limit: int | None
    features: list[str]


class SubscriptionOut(BaseModel):
    plan: PlanOut
    status: str
    billing_period: str
    current_period_end: datetime | None
    grace_until: datetime | None
    days_left: int | None
    assets_used: int
    members_used: int
    collectors_used: int
    available_plans: list[PlanOut]
    payment_provider: str
    # False until the first successful payment (so the UI can say "trial" rather than "plan").
    has_paid: bool
    annual_months_charged: int
    contact_email: str


class CheckoutRequest(BaseModel):
    plan_code: str
    billing_period: Period = "monthly"
    channel: Channel = "mobile_money"


class CheckoutOut(BaseModel):
    reference: str
    authorization_url: str
    amount_minor: int
    currency: str


class PaymentOut(BaseModel):
    id: uuid.UUID
    reference: str
    plan_code: str
    plan_name: str
    billing_period: str
    amount_minor: int
    currency: str
    channel: str
    status: str
    failure_reason: str | None
    payment_method: dict
    receipt: str | None
    credit_days: int
    period_start: datetime | None
    period_end: datetime | None
    paid_at: datetime | None
    created_at: datetime


class SandboxOutcome(BaseModel):
    outcome: Literal["success", "failed", "abandoned"]


def _plan_out(code: str) -> PlanOut:
    p = get_plan(code)
    annual = service.price_minor(p, "annual")
    return PlanOut(
        code=p.code,
        name=p.name,
        monthly_price_ghs=p.monthly_price_ghs,
        annual_price_ghs=annual // 100 if annual else None,
        asset_limit=p.asset_limit,
        member_limit=p.member_limit,
        collector_limit=p.collector_limit,
        features=list(p.features),
    )


def _payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        reference=p.reference,
        plan_code=p.plan_code,
        plan_name=get_plan(p.plan_code).name,
        billing_period=p.billing_period,
        amount_minor=p.amount_minor,
        currency=p.currency,
        channel=p.channel,
        status=p.status,
        failure_reason=p.failure_reason,
        payment_method=p.payment_method or {},
        receipt=service.receipt_label(p) or None,
        credit_days=p.credit_days,
        period_start=p.period_start,
        period_end=p.period_end,
        paid_at=p.paid_at,
        created_at=p.created_at,
    )


@router.get("/billing/subscription", response_model=SubscriptionOut)
def subscription(
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_READ)), db: Session = Depends(get_db)
) -> SubscriptionOut:
    sub = service.get_subscription(db, ctx.org_id)
    used = service.usage(db, ctx.org_id)
    status = service.effective_status(sub)
    end = sub.current_period_end
    now = datetime.now(UTC)
    return SubscriptionOut(
        plan=_plan_out(sub.plan_code),
        status=status,
        billing_period=sub.billing_period,
        current_period_end=end,
        grace_until=end + timedelta(days=settings.billing_grace_days)
        if end and sub.status != "trialing"
        else None,
        days_left=max(0, (end - now).days) if end and end > now else (0 if end else None),
        assets_used=used.assets,
        members_used=used.members,
        collectors_used=used.collectors,
        available_plans=[_plan_out(c) for c in PLANS],
        payment_provider=settings.payment_provider,
        has_paid=bool(
            db.scalar(
                select(Payment.id)
                .where(Payment.organisation_id == ctx.org_id, Payment.status == "success")
                .limit(1)
            )
        ),
        annual_months_charged=settings.annual_months_charged,
        contact_email=settings.billing_contact_email,
    )


@router.post("/billing/checkout", response_model=CheckoutOut, status_code=201)
def checkout(
    body: CheckoutRequest,
    request: Request,
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_MANAGE)),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    rate_limit(f"checkout:{ctx.org_id}", limit=20, window_seconds=3600)
    payment = service.start_checkout(
        db, ctx.organisation, ctx.user, body.plan_code, body.billing_period, body.channel
    )
    provider = get_provider(payment.provider)
    try:
        result = provider.initialize(
            reference=payment.reference,
            email=ctx.user.email,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            channel=payment.channel,
            callback_url=f"{settings.web_base_url}/settings/subscription/return",
            metadata={
                "organisation_id": str(ctx.org_id),
                "plan": payment.plan_code,
                "period": payment.billing_period,
            },
        )
    except ProviderError as exc:
        db.rollback()
        raise APIError(502, "payment_provider_error", str(exc)) from exc
    payment.provider_reference = result.provider_reference
    audit.record(
        db,
        "billing.checkout_started",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="payment",
        resource_id=payment.id,
        details={
            "plan": payment.plan_code,
            "period": payment.billing_period,
            "channel": payment.channel,
            "amount_minor": payment.amount_minor,
        },
        request=request,
    )
    db.commit()
    return CheckoutOut(
        reference=payment.reference,
        authorization_url=result.authorization_url,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
    )


@router.get("/billing/payments", response_model=Page[PaymentOut])
def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_READ)),
    db: Session = Depends(get_db),
) -> Page[PaymentOut]:
    # Attempts that were started and never finished are noise; show them only for a day.
    stmt = select(Payment).where(
        Payment.organisation_id == ctx.org_id,
        (Payment.status != "pending")
        | (Payment.created_at > datetime.now(UTC) - timedelta(days=1)),
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[PaymentOut](
        items=[_payment_out(p) for p in rows], total=total, page=page, page_size=page_size
    )


def _get_payment(db: Session, ctx: OrgContext, reference: str) -> Payment:
    payment = db.scalar(
        select(Payment).where(Payment.organisation_id == ctx.org_id, Payment.reference == reference)
    )
    if payment is None:
        raise APIError(404, "not_found", "Payment not found.")
    return payment


def _record_paid(db: Session, payment: Payment, request: Request | None, actor=None) -> None:
    audit.record(
        db,
        "billing.payment_succeeded",
        actor=actor,
        actor_label=None if actor else "Payment provider",
        organisation_id=payment.organisation_id,
        resource_type="payment",
        resource_id=payment.id,
        details={
            "plan": payment.plan_code,
            "period": payment.billing_period,
            "amount_minor": payment.amount_minor,
            "receipt": service.receipt_label(payment),
        },
        request=request,
    )


@router.post("/billing/payments/{reference}/verify", response_model=PaymentOut)
def verify_payment(
    reference: str,
    request: Request,
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_READ)),
    db: Session = Depends(get_db),
) -> PaymentOut:
    """Called when the customer returns from checkout. Asks the provider; never trusts the URL."""
    rate_limit(f"verify-pay:{ctx.user.id}", limit=30, window_seconds=300)
    payment = _get_payment(db, ctx, reference)
    if payment.status == "pending":
        try:
            result = get_provider(payment.provider).verify(payment.reference)
        except ProviderError as exc:
            raise APIError(502, "payment_provider_error", str(exc)) from exc
        if result.status == "success":
            if service.apply_success(
                db,
                payment,
                amount_minor=result.amount_minor,
                currency=result.currency,
                provider_reference=result.provider_reference,
                payment_method=result.payment_method,
            ):
                _record_paid(db, payment, request, ctx.user)
        elif result.status in {"failed", "abandoned"}:
            service.apply_failure(payment, result.status, result.failure_reason)
        db.commit()
    return _payment_out(payment)


@router.get("/billing/payments/{payment_id}/receipt")
def receipt(
    payment_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_READ)),
    db: Session = Depends(get_db),
) -> Response:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.organisation_id != ctx.org_id or payment.status != "success":
        raise APIError(404, "not_found", "Receipt not found.")
    pdf = render_receipt(payment, ctx.organisation)
    name = f"receipt-{service.receipt_label(payment)}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/billing/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Paystack calls this when a charge completes. Authenticated by its HMAC-SHA512 signature."""
    raw = await request.body()
    provider = PaystackProvider()
    if not provider.valid_signature(raw, request.headers.get("x-paystack-signature")):
        raise APIError(401, "invalid_signature", "Invalid signature.")
    try:
        event = json.loads(raw)
    except ValueError as exc:
        raise APIError(400, "invalid_payload", "Invalid payload.") from exc
    if event.get("event") != "charge.success":
        return {"status": "ignored"}
    reference = str((event.get("data") or {}).get("reference") or "")
    with system_context(db):
        payment = db.scalar(select(Payment).where(Payment.reference == reference))
    if payment is None:
        return {"status": "unknown_reference"}
    set_tenant_context(db, org=payment.organisation_id)
    # Re-check with the provider rather than trusting the webhook body's amount.
    try:
        result = provider.verify(reference)
    except ProviderError:
        raise APIError(502, "payment_provider_error", "Could not verify.") from None
    if result.status == "success" and service.apply_success(
        db,
        payment,
        amount_minor=result.amount_minor,
        currency=result.currency,
        provider_reference=result.provider_reference,
        payment_method=result.payment_method,
    ):
        _record_paid(db, payment, request)
    db.commit()
    return {"status": "ok"}


@router.post("/billing/sandbox/{reference}", response_model=PaymentOut, include_in_schema=False)
def sandbox_complete(
    reference: str,
    body: SandboxOutcome,
    request: Request,
    ctx: OrgContext = Depends(org_scope(Perm.BILLING_MANAGE)),
    db: Session = Depends(get_db),
) -> PaymentOut:
    """Development only: stands in for the provider's hosted checkout page."""
    if not settings.is_development or settings.payment_provider != "sandbox":
        raise APIError(404, "not_found", "Not found.")
    payment = _get_payment(db, ctx, reference)
    if payment.status != "pending":
        return _payment_out(payment)
    if body.outcome == "success":
        method = (
            {"brand": "visa", "last4": "4081"}
            if payment.channel == "card"
            else {"network": "MTN", "phone": "*****789"}
        )
        if service.apply_success(
            db,
            payment,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            provider_reference=f"sandbox-{payment.reference[-8:]}",
            payment_method=method,
        ):
            _record_paid(db, payment, request, ctx.user)
    else:
        service.apply_failure(
            payment,
            body.outcome,
            "Declined in the test checkout." if body.outcome == "failed" else "Checkout cancelled.",
        )
    db.commit()
    return _payment_out(payment)
