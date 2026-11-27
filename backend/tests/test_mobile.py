import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.main import app
from app.models import Notification, PushDevice
from app.services import push
from tests.conftest import PASSWORD, enable_mfa, invite_and_join, register
from tests.test_monitoring_engine import authorised_website, bad_headers, run


@pytest.fixture
def system_db():
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    yield db
    db.close()


class Phone:
    """The mobile app: bearer tokens, no cookies, no CSRF header."""

    def __init__(self) -> None:
        self.client = TestClient(app)
        self.tokens: dict | None = None
        self.org_id: str | None = None

    def headers(self) -> dict:
        h = {"user-agent": "SMECM-Mobile/1.0 (iOS 19)"}
        if self.tokens:
            h["authorization"] = f"Bearer {self.tokens['access_token']}"
        if self.org_id:
            h["x-organisation-id"] = self.org_id
        return h

    def login(self, identifier: str, password: str = PASSWORD) -> dict:
        r = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": identifier, "password": password, "client": "mobile"},
            headers=self.headers(),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if body["tokens"]:
            self.tokens = body["tokens"]
        self.client.cookies.clear()
        return body

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers(), **kw)

    def post(self, url, json=None):
        return self.client.post(url, json=json, headers=self.headers())

    def put(self, url, json=None):
        return self.client.put(url, json=json, headers=self.headers())

    def delete(self, url):
        return self.client.delete(url, headers=self.headers())

    def register_device(self, token="fcm-token-0123456789abcdef", platform="ios"):  # noqa: S107
        r = self.post(
            "/api/v1/me/push-devices",
            {
                "platform": platform,
                "token": token,
                "device_name": "Ama's iPhone",
                "app_version": "1.0.0",
            },
        )
        assert r.status_code == 201, r.text
        return r.json()


@pytest.fixture
def phone(owner):
    p = Phone()
    body = p.login("owner@acme.example.com")
    p.org_id = body["me"]["memberships"][0]["organisation_id"]
    return p


def test_mobile_login_returns_tokens_and_sets_no_cookies(owner):
    p = Phone()
    r = p.client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner@acme.example.com", "password": PASSWORD, "client": "mobile"},
    )
    body = r.json()
    assert body["status"] == "ok" and body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] == 15 * 60
    assert "set-cookie" not in r.headers
    # Web sign-in is unchanged: cookies, no tokens in the body.
    web = TestClient(app).post(
        "/api/v1/auth/login", json={"identifier": "owner@acme.example.com", "password": PASSWORD}
    )
    assert web.json()["tokens"] is None and "smecm_access" in web.cookies


def test_bearer_requests_work_without_csrf(phone):
    assert phone.get("/api/v1/overview").status_code == 200
    r = phone.put("/api/v1/notifications/preferences", {"push_min_severity": "medium"})
    assert r.status_code == 200 and r.json()["push_min_severity"] == "medium"


def test_mobile_refresh_rotates_and_detects_reuse(phone):
    old = phone.tokens
    r = phone.client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert r.status_code == 200, r.text
    new = r.json()["tokens"]
    assert new["refresh_token"] != old["refresh_token"]
    phone.tokens = new
    assert phone.get("/api/v1/auth/me").status_code == 200

    # Presenting the old token again ends the session: someone copied it.
    r = phone.client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert r.status_code == 401
    assert phone.get("/api/v1/auth/me").status_code == 401


def test_a_web_refresh_token_cannot_be_used_as_a_mobile_one(owner):
    web_refresh = owner.client.cookies.get("smecm_refresh")
    r = TestClient(app).post("/api/v1/auth/refresh", json={"refresh_token": web_refresh})
    assert r.status_code == 401


def test_mobile_mfa_sign_in(owner):
    totp = enable_mfa(owner)
    p = Phone()
    body = p.login("owner@acme.example.com")
    assert body["status"] == "mfa_required" and body["tokens"] is None
    r = p.client.post(
        "/api/v1/auth/mfa/verify",
        # The next 30-second code: the current one was just used to turn MFA on.
        json={
            "mfa_token": body["mfa_token"],
            "code": totp.at(time.time() + 30),
            "client": "mobile",
        },
    )
    assert r.status_code == 200 and r.json()["tokens"]["access_token"]


def test_device_registration_is_private_to_its_owner(phone, owner):
    device = phone.register_device()
    assert device["this_device"] and device["platform"] == "ios"
    # Re-registering the same token refreshes the same row.
    assert phone.register_device()["id"] == device["id"]
    assert len(phone.get("/api/v1/me/push-devices").json()) == 1

    analyst = invite_and_join(owner, "analyst@acme.example.com", "security_analyst")
    assert analyst.get("/api/v1/me/push-devices").json() == []
    assert analyst.delete(f"/api/v1/me/push-devices/{device['id']}").status_code == 404

    # Someone else can't claim a token while its owner is still signed in on that phone...
    p2 = Phone()
    p2.login("analyst@acme.example.com")
    r = p2.post(
        "/api/v1/me/push-devices",
        {"platform": "ios", "token": "fcm-token-0123456789abcdef"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "device_in_use"
    # ...but once the owner signs out, the next person on the phone takes it over.
    phone.post("/api/v1/auth/logout")
    p2.register_device()
    assert len(p2.get("/api/v1/me/push-devices").json()) == 1


def test_push_token_is_encrypted_at_rest(phone, system_db):
    phone.register_device(token="fcm-secret-token-abcdefghijkl")
    row = system_db.scalar(select(PushDevice))
    assert "fcm-secret-token" not in row.token_encrypted and len(row.token_hash) == 64


def test_alerts_are_pushed_by_severity_preference(phone, owner, monkeypatch, system_db):
    phone.register_device()
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())  # medium findings
    assert push.dispatch_pending(system_db) == 0  # default push threshold is high
    assert system_db.scalar(select(Notification).where(Notification.pushed_at.is_(None))) is None

    phone.put("/api/v1/notifications/preferences", {"push_min_severity": "low"})
    from app.monitoring import checks

    run(
        system_db,
        "tls",
        asset["id"],
        checks.Outcome(
            "warning", "x", issues=[checks.Issue("tls_certificate_expired")], reachable=True
        ),
    )
    assert push.dispatch_pending(system_db) == 2  # the alert, and the incident it opened
    sent = {p["data"]["link"].split("/")[1]: p for p in push.read_dev_pushes()}
    assert sent["alerts"]["title"].startswith("Critical · Acme Ltd")
    assert sent["incidents"]["body"].startswith("New critical incident")
    # Lock-screen privacy: the body names the alert but not the asset details.
    assert "shop.example.com" not in sent["alerts"]["body"]


def test_old_notifications_are_not_pushed(phone, owner, monkeypatch, system_db):
    phone.register_device()
    phone.put("/api/v1/notifications/preferences", {"push_min_severity": "low"})
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    system_db.execute(
        update(Notification).values(created_at=datetime.now(UTC) - timedelta(hours=2))
    )
    system_db.commit()
    assert push.dispatch_pending(system_db) == 0


def test_signing_out_stops_pushes_to_that_phone(phone, owner, monkeypatch, system_db):
    phone.register_device()
    phone.put("/api/v1/notifications/preferences", {"push_min_severity": "low"})
    assert phone.post("/api/v1/auth/logout").status_code == 200
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    assert push.dispatch_pending(system_db) == 0


def test_invalid_tokens_are_disabled(phone, owner, monkeypatch, system_db):
    phone.register_device()

    def gone(*a, **kw):
        raise push.InvalidToken("UNREGISTERED")

    monkeypatch.setattr(push.LogProvider, "send", gone)
    r = phone.post("/api/v1/me/push-devices/test")
    assert r.status_code == 502
    device = phone.get("/api/v1/me/push-devices").json()[0]
    assert device["enabled"] is False and "uninstalled" in device["last_error"]


def test_test_push(phone):
    assert phone.post("/api/v1/me/push-devices/test").status_code == 404
    phone.register_device()
    r = phone.post("/api/v1/me/push-devices/test")
    assert r.status_code == 200 and "1 device" in r.json()["message"]
    assert "Test notification" in push.read_dev_pushes()[0]["body"]


def test_dev_push_outbox(phone):
    phone.register_device()
    phone.post("/api/v1/me/push-devices/test")
    assert len(register("x@y.example.com").get("/api/v1/dev/push").json()) == 1
