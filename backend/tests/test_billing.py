import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import ProgrammingError

from app.billing import providers, service
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Payment, Subscription
from app.services.email import read_dev_mailbox
from tests.conftest import create_org, invite_and_join, register


@pytest.fixture
def system_db():
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    yield db
    db.close()


def checkout(api, plan="business", period="monthly", channel="mobile_money"):
    r = api.post(
        "/api/v1/billing/checkout",
        {"plan_code": plan, "billing_period": period, "channel": channel},
    )
    assert r.status_code == 201, r.text
    return r.json()


def pay(api, plan="business", period="monthly", channel="mobile_money", outcome="success"):
    ref = checkout(api, plan, period, channel)["reference"]
    r = api.post(f"/api/v1/billing/sandbox/{ref}", {"outcome": outcome})
    assert r.status_code == 200, r.text
    return r.json()


def set_sub(db, **values):
    db.execute(update(Subscription).values(**values))
    db.commit()


def test_new_workspace_starts_on_a_trial_with_prices_and_usage(owner):
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["status"] == "trialing" and sub["plan"]["code"] == "starter"
    assert 13 <= sub["days_left"] <= 14
    assert sub["payment_provider"] == "sandbox"
    business = next(p for p in sub["available_plans"] if p["code"] == "business")
    assert business["monthly_price_ghs"] == 350
    assert business["annual_price_ghs"] == 3500  # ten months for twelve
    enterprise = next(p for p in sub["available_plans"] if p["code"] == "enterprise")
    assert enterprise["monthly_price_ghs"] is None


def test_mobile_money_checkout_activates_the_plan_and_issues_a_receipt(owner):
    started = checkout(owner)
    assert started["amount_minor"] == 35000 and started["currency"] == "GHS"
    assert started["authorization_url"].startswith(f"{settings.web_base_url}/billing/sandbox")

    paid = owner.post(f"/api/v1/billing/sandbox/{started['reference']}", {"outcome": "success"})
    body = paid.json()
    assert body["status"] == "success" and body["receipt"].endswith("-00001")
    assert body["payment_method"] == {"network": "MTN", "phone": "*****789"}

    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["status"] == "active" and sub["plan"]["code"] == "business"
    assert 29 <= sub["days_left"] <= 30

    # Returning from checkout re-checks, and a second confirmation changes nothing.
    again = owner.post(f"/api/v1/billing/payments/{started['reference']}/verify").json()
    assert again["receipt"] == body["receipt"]

    history = owner.get("/api/v1/billing/payments").json()
    assert history["total"] == 1
    pdf = owner.get(f"/api/v1/billing/payments/{body['id']}/receipt")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    actions = [e["action"] for e in owner.get("/api/v1/audit-logs").json()["items"]]
    assert "billing.payment_succeeded" in actions and "billing.checkout_started" in actions


def test_declined_payment_leaves_the_subscription_unchanged(owner):
    result = pay(owner, outcome="failed")
    assert result["status"] == "failed" and result["receipt"] is None
    assert owner.get("/api/v1/billing/subscription").json()["status"] == "trialing"
    r = owner.get(f"/api/v1/billing/payments/{result['id']}/receipt")
    assert r.status_code == 404


def test_annual_card_payment_buys_a_year(owner):
    paid = pay(owner, plan="starter", period="annual", channel="card")
    assert paid["amount_minor"] == 150000
    assert paid["payment_method"]["last4"] == "4081"
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["billing_period"] == "annual" and sub["days_left"] >= 364


def test_early_renewal_extends_from_the_current_end(owner):
    first = pay(owner)
    second = pay(owner)
    assert second["period_start"] == first["period_end"]
    assert second["receipt"].endswith("-00002")


def test_upgrade_credits_unused_time(owner, system_db):
    pay(owner, plan="business")  # 30 days of GH₵350
    upgraded = pay(owner, plan="professional")  # GH₵750/30 days
    # ~30 days × 350/750 ≈ 13-14 days credited on top of the new 30.
    assert 13 <= upgraded["credit_days"] <= 14
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["plan"]["code"] == "professional" and sub["days_left"] >= 42


def test_cannot_downgrade_below_current_usage(owner, system_db):
    pay(owner, plan="business")
    for i in range(6):
        r = owner.post(
            "/api/v1/assets", {"name": f"Site {i}", "type": "website", "identifier": f"s{i}.ex.com"}
        )
        assert r.status_code == 201, r.text
    r = owner.post(
        "/api/v1/billing/checkout",
        {"plan_code": "starter", "billing_period": "monthly", "channel": "card"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "plan_too_small"
    assert "6 active assets" in r.json()["error"]["message"]


def test_enterprise_is_contact_sales(owner):
    r = owner.post("/api/v1/billing/checkout", {"plan_code": "enterprise"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "contact_sales"


def test_only_owners_can_pay_but_admins_can_see_billing(owner):
    admin = invite_and_join(owner, "admin@acme.example.com", "admin")
    assert admin.get("/api/v1/billing/subscription").status_code == 200
    r = admin.post("/api/v1/billing/checkout", {"plan_code": "business"})
    assert r.status_code == 403
    analyst = invite_and_join(owner, "analyst@acme.example.com", "security_analyst")
    assert analyst.get("/api/v1/billing/subscription").status_code == 403


def test_payments_are_isolated_between_organisations(owner):
    ref = checkout(owner)["reference"]
    other = register("other@beta.example.com")
    create_org(other, "Beta Ltd")
    assert other.post(f"/api/v1/billing/payments/{ref}/verify").status_code == 404
    assert other.post(f"/api/v1/billing/sandbox/{ref}", {"outcome": "success"}).status_code == 404
    assert other.get("/api/v1/billing/payments").json()["total"] == 0


def test_payment_with_the_wrong_amount_never_activates(owner, system_db):
    ref = checkout(owner)["reference"]
    payment = system_db.scalar(select(Payment).where(Payment.reference == ref))
    applied = service.apply_success(system_db, payment, amount_minor=100, currency="GHS")
    system_db.commit()
    assert applied is False and payment.status == "failed"
    assert owner.get("/api/v1/billing/subscription").json()["status"] == "trialing"


def test_payment_records_cannot_be_deleted_by_the_application(owner, system_db):
    pay(owner)
    with pytest.raises(ProgrammingError):
        system_db.execute(text("DELETE FROM payments"))
    system_db.rollback()


# --- Lifecycle ----------------------------------------------------------------------------


def test_trial_reminders_then_expiry_blocks_growth_but_keeps_data(owner, system_db):
    now = datetime.now(UTC)
    set_sub(system_db, current_period_end=now + timedelta(days=2, hours=12))
    assert service.sweep_subscriptions(system_db) == 1
    mail = read_dev_mailbox()[0]
    assert "ends in 3 days" in mail["subject"] and mail["to"] == "owner@acme.example.com"
    # Each reminder goes out once.
    assert service.sweep_subscriptions(system_db) == 0

    set_sub(system_db, current_period_end=now - timedelta(minutes=1))
    service.sweep_subscriptions(system_db)
    assert "free trial has ended" in read_dev_mailbox()[0]["subject"]
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["status"] == "expired"

    r = owner.post("/api/v1/assets", {"name": "Shop", "type": "website", "identifier": "a.ex.com"})
    assert r.status_code == 402 and r.json()["error"]["code"] == "subscription_lapsed"
    r = owner.post(
        f"/api/v1/organisations/{owner.org_id}/invitations",
        {"email": "x@acme.example.com", "role": "security_analyst"},
    )
    assert r.status_code == 402
    assert owner.get("/api/v1/assets").status_code == 200  # data is still there

    pay(owner)
    assert owner.get("/api/v1/billing/subscription").json()["status"] == "active"
    r = owner.post("/api/v1/assets", {"name": "Shop", "type": "website", "identifier": "a.ex.com"})
    assert r.status_code == 201


def test_paid_plan_goes_past_due_with_grace_then_expires(owner, system_db):
    pay(owner)
    now = datetime.now(UTC)
    set_sub(system_db, current_period_end=now - timedelta(days=1))
    service.sweep_subscriptions(system_db)
    assert "Payment due" in read_dev_mailbox()[0]["subject"]
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["status"] == "past_due" and sub["grace_until"]
    # Still allowed to work during the grace period.
    r = owner.post("/api/v1/assets", {"name": "Shop", "type": "website", "identifier": "b.ex.com"})
    assert r.status_code == 201

    set_sub(system_db, current_period_end=now - timedelta(days=settings.billing_grace_days + 1))
    service.sweep_subscriptions(system_db)
    assert owner.get("/api/v1/billing/subscription").json()["status"] == "expired"


# --- Paystack -----------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


def test_paystack_initialize_verify_and_signed_webhook(owner, monkeypatch, system_db):
    monkeypatch.setattr(settings, "payment_provider", "paystack")
    monkeypatch.setattr(settings, "paystack_secret_key", "sk_test_dummy")
    calls = {}

    class FakeClient:
        def __init__(self, *a, **kw):
            calls["auth"] = kw["headers"]["Authorization"]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json):
            calls["init"] = json
            return FakeResponse(
                200,
                {
                    "status": True,
                    "data": {
                        "authorization_url": "https://checkout.paystack.com/abc",
                        "access_code": "abc",
                    },
                },
            )

        def get(self, url):
            ref = url.rsplit("/", 1)[1]
            return FakeResponse(
                200,
                {
                    "status": True,
                    "data": {
                        "id": 4242,
                        "reference": ref,
                        "status": "success",
                        "amount": calls["init"]["amount"],
                        "currency": "GHS",
                        "channel": "mobile_money",
                        "authorization": {"bank": "MTN", "mobile_money_number": "0241234567"},
                    },
                },
            )

    monkeypatch.setattr(providers.httpx, "Client", FakeClient)
    started = checkout(owner, plan="business", channel="mobile_money")
    assert started["authorization_url"] == "https://checkout.paystack.com/abc"
    assert calls["init"]["channels"] == ["mobile_money"] and calls["init"]["amount"] == 35000
    assert calls["auth"] == "Bearer sk_test_dummy"

    raw = json.dumps(
        {"event": "charge.success", "data": {"reference": started["reference"], "amount": 1}}
    ).encode()
    bad = owner.client.post(
        "/api/v1/billing/webhooks/paystack",
        content=raw,
        headers={"x-paystack-signature": "0" * 128, "content-type": "application/json"},
    )
    assert bad.status_code == 401

    sig = hmac.new(b"sk_test_dummy", raw, hashlib.sha512).hexdigest()
    ok = owner.client.post(
        "/api/v1/billing/webhooks/paystack",
        content=raw,
        headers={"x-paystack-signature": sig, "content-type": "application/json"},
    )
    assert ok.status_code == 200, ok.text
    sub = owner.get("/api/v1/billing/subscription").json()
    assert sub["status"] == "active" and sub["plan"]["code"] == "business"
    payment = owner.get("/api/v1/billing/payments").json()["items"][0]
    # The webhook body said amount 1; we trusted the provider's verified amount instead.
    assert payment["amount_minor"] == 35000
    assert payment["payment_method"] == {"network": "MTN", "phone": "*****567"}

    # The sandbox endpoint is disabled when a real provider is configured.
    ref2 = checkout(owner)["reference"]
    assert owner.post(f"/api/v1/billing/sandbox/{ref2}", {"outcome": "success"}).status_code == 404
