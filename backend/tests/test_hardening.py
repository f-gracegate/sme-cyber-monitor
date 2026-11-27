"""Phase 7 pre-launch security fixes."""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.monitoring import net
from app.services.email import read_dev_mailbox
from tests.conftest import PASSWORD, create_org, enable_mfa, invite_and_join, register
from tests.test_endpoints import enrol, new_token
from tests.test_monitoring_rules import resp


def login(identifier: str, password: str = PASSWORD) -> tuple[TestClient, dict]:
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return client, r


# --- Configuration fails closed --------------------------------------------------------------


def test_unset_environment_means_production_and_refuses_weak_settings(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


# --- MFA -------------------------------------------------------------------------------------


def test_mfa_token_allows_few_attempts_and_works_once(owner):
    totp = enable_mfa(owner)
    client, r = login("owner@acme.example.com")
    mfa_token = r.json()["mfa_token"]
    for _ in range(5):
        bad = client.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"}
        )
        assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_mfa_code"
    # The sixth try is refused even with the right code: sign in again.
    code = totp.at(time.time() + 30)
    sixth = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code})
    assert sixth.json()["error"]["code"] in {"mfa_token_expired", "account_locked"}


def test_mfa_token_cannot_be_reused(owner):
    totp = enable_mfa(owner)
    client, r = login("owner@acme.example.com")
    mfa_token = r.json()["mfa_token"]
    ok = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": totp.at(time.time() + 30)},
    )
    assert ok.status_code == 200
    again = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": totp.at(time.time() + 60)},
    )
    assert again.status_code == 401


def test_wrong_mfa_codes_lock_the_account(owner):
    enable_mfa(owner)
    for _ in range(5):
        client, r = login("owner@acme.example.com")
        client.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": r.json()["mfa_token"], "code": "111111"}
        )
    _, r = login("owner@acme.example.com")
    assert r.status_code == 423


def test_turning_mfa_off_signs_out_other_sessions(owner):
    totp = enable_mfa(owner)
    other, r = login("owner@acme.example.com")
    other.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": r.json()["mfa_token"], "code": totp.at(time.time() + 30)},
    )
    assert other.get("/api/v1/auth/me").status_code == 200
    # Codes can't be replayed, so let the next 30-second step be used again for this test.
    from sqlalchemy import update

    from app.core.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(User).values(mfa_last_used_step=None))
    db.commit()
    db.close()
    r = owner.post(
        "/api/v1/auth/mfa/disable",
        {"password": PASSWORD, "code": totp.at(time.time() + 30)},
    )
    assert r.status_code == 200, r.text
    assert other.get("/api/v1/auth/me").status_code == 401
    assert owner.get("/api/v1/auth/me").status_code == 200


# --- Account enumeration ---------------------------------------------------------------------


def test_unknown_accounts_lock_like_real_ones(owner):
    for _ in range(5):
        _, r = login("nobody@acme.example.com", "wrong-password")
        assert r.status_code == 401
    _, r = login("nobody@acme.example.com", "wrong-password")
    assert r.status_code == 423


# --- Email verification ----------------------------------------------------------------------


def test_workspace_needs_a_confirmed_email():
    api = register("new@biz.example.com", verify=False)
    r = api.post("/api/v1/organisations", {"name": "Biz Ltd"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"
    assert api.get("/api/v1/auth/me").json()["user"]["email_verified_at"] is None
    from tests.conftest import verify_email

    verify_email(api, "new@biz.example.com")
    assert api.post("/api/v1/organisations", {"name": "Biz Ltd"}).status_code == 201


def test_verification_link_is_bound_to_the_address():
    api = register("x@biz.example.com", verify=False)
    mail = read_dev_mailbox()[0]
    token = mail["body"].split("verify-email?token=")[1].split()[0]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert api.post("/api/v1/auth/email/verify", {"token": tampered}).status_code == 400


def test_invited_people_are_verified_by_the_invitation(owner):
    member = invite_and_join(owner, "it@acme.example.com", "it_admin")
    assert member.get("/api/v1/auth/me").json()["user"]["email_verified_at"]


def test_reset_on_an_unverified_account_clears_a_squatters_mfa():
    # An attacker registers the victim's address and turns on MFA to lock them out.
    squatter = register("victim@corp.example.com", verify=False)
    enable_mfa(squatter)
    # The real owner resets the password from their inbox.
    TestClient(app).post("/api/v1/auth/password/forgot", json={"email": "victim@corp.example.com"})
    mail = next(m for m in read_dev_mailbox() if "reset-password" in m["body"])
    token = mail["body"].split("reset-password?token=")[1].split()[0]
    r = TestClient(app).post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "Owner-Gets-Back-77"}
    )
    assert r.status_code == 200, r.text
    _, r = login("victim@corp.example.com", "Owner-Gets-Back-77")
    assert r.json()["status"] == "ok"  # no squatter MFA in the way
    assert squatter.get("/api/v1/auth/me").status_code == 401  # squatter's session ended


# --- Devices ---------------------------------------------------------------------------------


def test_an_enrolled_device_cannot_be_taken_over_with_a_token(owner):
    assert enrol(new_token(owner)).status_code == 200
    r = enrol(new_token(owner))  # same machine_id, fresh token
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"


def test_lapsed_subscription_blocks_new_devices(owner):
    from sqlalchemy import update

    from app.core.db import SessionLocal
    from app.models import Subscription

    token = new_token(owner)
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(Subscription).values(status="expired"))
    db.commit()
    db.close()
    r = enrol(token)
    assert r.status_code == 402 and r.json()["error"]["code"] == "subscription_lapsed"


# --- Monitoring redirects --------------------------------------------------------------------


def test_redirects_are_followed_only_within_the_site(monkeypatch):
    seen = []

    def fake(url, timeout):
        seen.append(url)
        if url == "https://shop.example.com/":
            return resp(301, [("location", "https://www.example.com/")])
        if url == "https://www.example.com/":
            return resp(302, [("location", "http://tracker.example.net:8080/x")])
        return resp(200)

    monkeypatch.setattr(net, "_request", fake)
    monkeypatch.setattr(net, "resolve_public_addresses", lambda host: ["93.184.216.34"])
    result = net.fetch("https://shop.example.com/")
    assert seen == ["https://shop.example.com/", "https://www.example.com/"]
    assert result.ok and result.error == "Redirects to another site"
    assert net.site_of("shop.example.com.gh") == "example.com.gh"
    assert not net.same_site_redirect("https://a.example.com/", "https://a.example.com:8443/")


# --- Staff overview --------------------------------------------------------------------------


def test_staff_overview_leaves_out_security_detail(owner):
    staff = invite_and_join(owner, "staff@acme.example.com", "employee")
    o = staff.get("/api/v1/overview").json()
    assert o["limited"] is True
    assert o["recent_alerts"] == [] and o["posture_score"] is None
    assert o["members_with_mfa"] == 0
    assert owner.get("/api/v1/overview").json()["limited"] is False


def test_staff_can_still_create_another_workspace_only_when_verified():
    api = register("solo@biz.example.com")
    assert create_org(api, "Solo Ltd")


# --- Platform observability ------------------------------------------------------------------


def test_metrics_need_a_token_and_never_include_raw_ids(owner, monkeypatch):
    from app.core.config import settings

    owner.get("/api/v1/overview")
    owner.get(f"/api/v1/organisations/{owner.org_id}")
    client = TestClient(app)
    assert client.get("/api/metrics").status_code == 404  # disabled without METRICS_TOKEN
    monkeypatch.setattr(settings, "metrics_token", "m" * 32)
    assert client.get("/api/metrics", headers={"authorization": "Bearer wrong"}).status_code == 404
    r = client.get("/api/metrics", headers={"authorization": f"Bearer {'m' * 32}"})
    assert r.status_code == 200
    assert 'route="/api/v1/overview"' in r.text
    assert 'route="/api/v1/organisations/{org_id}"' in r.text
    assert owner.org_id not in r.text
    assert "smecm_checks_overdue" in r.text
    assert "worker" in client.get("/api/health").json()
