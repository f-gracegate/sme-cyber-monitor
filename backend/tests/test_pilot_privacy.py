import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import (
    Alert,
    AuditLog,
    IncidentEvent,
    Organisation,
    SecurityEvent,
    User,
)
from app.monitoring import checks
from app.privacy import service as privacy
from tests.conftest import PASSWORD, create_org, invite_and_join, register
from tests.test_monitoring_engine import authorised_website, bad_headers, run


@pytest.fixture
def system_db():
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    yield db
    db.close()


def make_platform_admin(email: str) -> None:
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(User).where(User.email == email).values(is_platform_admin=True))
    db.commit()
    db.close()


def open_alerts(api) -> list[dict]:
    return api.get("/api/v1/alerts").json()["items"]


# --- Alert outcomes and muting ----------------------------------------------------------------


def test_false_positives_feed_the_pilot_metrics(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    a, b = open_alerts(owner)[:2]
    r = owner.patch(
        f"/api/v1/alerts/{a['id']}", {"status": "resolved", "outcome": "false_positive"}
    )
    assert r.json()["outcome"] == "false_positive"
    owner.patch(f"/api/v1/alerts/{b['id']}", {"status": "resolved"})

    assert owner.get("/api/v1/platform/pilot-metrics").status_code == 403
    make_platform_admin("owner@acme.example.com")
    org = owner.get("/api/v1/platform/pilot-metrics").json()["organisations"][0]
    assert org["false_positive_pct"] == 50 and org["alerts_30d"] == 2
    assert org["assets"] == 1 and org["members"] == 1 and org["subscription"] == "trialing"


def test_muting_stops_new_alerts_but_keeps_findings(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    alert = next(a for a in open_alerts(owner) if "HSTS" in a["title"])
    r = owner.post(
        "/api/v1/suppression-rules",
        {"alert_id": alert["id"], "reason": "Handled by our CDN", "expires_in_days": 30},
    )
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["asset_name"] == "Shop" and rule["rule_key"] == "missing_hsts"
    assert all("HSTS" not in a["title"] for a in open_alerts(owner))  # closed as expected

    # The problem clears and comes back: the finding reopens but no alert is raised.
    run(system_db, "security_headers", asset["id"], checks.Outcome("ok", "fine", reachable=True))
    run(system_db, "security_headers", asset["id"], bad_headers())
    assert all("HSTS" not in a["title"] for a in open_alerts(owner))
    findings = owner.get("/api/v1/findings").json()["items"]
    assert any(f["rule_key"] == "missing_hsts" and f["status"] == "open" for f in findings)
    assert owner.get("/api/v1/suppression-rules").json()[0]["hits"] == 1

    assert owner.delete(f"/api/v1/suppression-rules/{rule['id']}").status_code == 204
    assert owner.get("/api/v1/suppression-rules").json() == []


def test_critical_alerts_cannot_be_muted_and_staff_cannot_mute(owner):
    r = owner.post(
        "/api/v1/suppression-rules",
        {"rule_key": "tls_certificate_expired", "all_assets": True, "reason": "noise"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "cannot_mute_critical"
    staff = invite_and_join(owner, "staff@acme.example.com", "employee")
    r = staff.post(
        "/api/v1/suppression-rules",
        {"rule_key": "missing_hsts", "all_assets": True, "reason": "noise"},
    )
    assert r.status_code == 403


def test_muting_rules_are_private_to_the_organisation(owner, system_db):
    owner.post(
        "/api/v1/suppression-rules",
        {"rule_key": "missing_hsts", "all_assets": True, "reason": "CDN"},
    )
    other = register("x@beta.example.com")
    create_org(other, "Beta Ltd")
    assert other.get("/api/v1/suppression-rules").json() == []
    rule_id = owner.get("/api/v1/suppression-rules").json()[0]["id"]
    assert other.delete(f"/api/v1/suppression-rules/{rule_id}").status_code == 404


# --- Feedback ---------------------------------------------------------------------------------


def test_feedback_reaches_the_platform_team(owner):
    r = owner.post(
        "/api/v1/feedback", {"kind": "idea", "message": "Add WhatsApp alerts", "rating": 4}
    )
    assert r.status_code == 201
    assert owner.get("/api/v1/platform/feedback").status_code == 403
    make_platform_admin("owner@acme.example.com")
    items = owner.get("/api/v1/platform/feedback").json()
    assert (
        items[0]["message"] == "Add WhatsApp alerts" and items[0]["organisation_name"] == "Acme Ltd"
    )
    fid = items[0]["id"]
    assert owner.patch(f"/api/v1/platform/feedback/{fid}", {"status": "done"}).status_code == 200


# --- Retention --------------------------------------------------------------------------------


def test_retention_follows_the_plan_and_prunes_old_telemetry(owner, system_db):
    url = f"/api/v1/organisations/{owner.org_id}/retention"
    assert owner.get(url).json() == {"telemetry_retention_days": 30, "max_days": 30}
    r = owner.client.put(url, json={"telemetry_retention_days": 90}, headers=owner._headers())
    assert r.status_code == 422 and r.json()["error"]["code"] == "retention_above_plan"
    r = owner.client.put(url, json={"telemetry_retention_days": 14}, headers=owner._headers())
    assert r.status_code == 200

    from tests.test_endpoints import enrol, failure, new_token, send_events

    cred = enrol(new_token(owner)).json()["credential"]
    send_events(cred, [failure(i) for i in range(3)])
    system_db.execute(
        update(SecurityEvent).values(received_at=datetime.now(UTC) - timedelta(days=20))
    )
    system_db.commit()
    privacy.prune_telemetry(system_db)
    assert system_db.scalar(select(func.count()).select_from(SecurityEvent)) == 0


# --- Export -----------------------------------------------------------------------------------


def test_data_export_contains_records_but_no_secrets(owner):
    owner.post("/api/v1/assets", {"name": "Shop", "type": "website", "identifier": "a.ex.com"})
    url = f"/api/v1/organisations/{owner.org_id}/exports"
    export = owner.post(url).json()
    assert export["status"] == "ready" and "1 assets" in export["summary"]
    dl = owner.get(f"{url}/{export['id']}/download")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    assert json.loads(zf.read("assets.json"))[0]["identifier"].endswith("a.ex.com")
    assert json.loads(zf.read("members.json"))[0]["email"] == "owner@acme.example.com"
    everything = b"".join(zf.read(n) for n in zf.namelist())
    assert b"password_hash" not in everything and b"argon2" not in everything

    analyst = invite_and_join(owner, "it@acme.example.com", "it_admin")
    assert analyst.post(url).status_code == 403
    actions = [e["action"] for e in owner.get("/api/v1/audit-logs").json()["items"]]
    assert "organisation.data_exported" in actions
    assert "organisation.data_export_downloaded" in actions


# --- Organisation deletion --------------------------------------------------------------------


def test_organisation_deletion_has_a_cooling_off_period_then_erases(owner, system_db):
    owner.post("/api/v1/assets", {"name": "Shop", "type": "website", "identifier": "a.ex.com"})
    inc = owner.post("/api/v1/incidents", {"title": "Phishing", "category": "phishing"}).json()
    owner.client.post(
        f"/api/v1/incidents/{inc['id']}/evidence",
        files={"file": ("mail.eml", b"From: x", "message/rfc822")},
        headers=owner._headers(),
    )
    url = f"/api/v1/organisations/{owner.org_id}/deletion"
    bad = owner.post(url, {"confirm_name": "Acme", "password": PASSWORD})
    assert bad.status_code == 422
    r = owner.post(url, {"confirm_name": "Acme Ltd", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["scheduled_for"]
    # Cancel and request again.
    assert owner.delete(url).json()["scheduled_for"] is None
    owner.post(url, {"confirm_name": "Acme Ltd", "password": PASSWORD})

    # Not yet due: nothing happens.
    assert privacy.run_due_erasures(system_db) == 0
    system_db.execute(
        update(Organisation).values(deletion_scheduled_for=datetime.now(UTC) - timedelta(days=1))
    )
    system_db.commit()
    assert privacy.run_due_erasures(system_db) == 1

    system_db.expire_all()
    org = system_db.get(Organisation, __import__("uuid").UUID(owner.org_id))
    assert org.name == "Deleted organisation" and org.deleted_at is not None
    assert system_db.scalar(select(func.count()).select_from(IncidentEvent)) == 0
    assert system_db.scalar(select(func.count()).select_from(Alert)) == 0
    assert not (Path(settings.storage_dir) / owner.org_id).exists()
    # The audit trail is a legal record and stays.
    assert (
        system_db.scalar(select(func.count()).where(AuditLog.action == "organisation.erased")) == 1
    )
    assert owner.get("/api/v1/auth/me").json()["memberships"] == []
    assert owner.get("/api/v1/assets").status_code == 404


def test_only_owners_can_delete_the_organisation(owner):
    admin = invite_and_join(owner, "admin@acme.example.com", "admin")
    r = admin.post(
        f"/api/v1/organisations/{owner.org_id}/deletion",
        {"confirm_name": "Acme Ltd", "password": PASSWORD},
    )
    assert r.status_code == 403


# --- Account deletion -------------------------------------------------------------------------


def test_account_deletion(owner, system_db):
    r = owner.post("/api/v1/me/delete-account", {"password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_owner"

    member = invite_and_join(owner, "it@acme.example.com", "it_admin")
    assert member.post("/api/v1/me/delete-account", {"password": "nope"}).status_code == 400
    assert member.post("/api/v1/me/delete-account", {"password": PASSWORD}).status_code == 200
    assert member.get("/api/v1/auth/me").status_code == 401
    user = system_db.scalar(select(User).where(User.full_name == "Deleted user"))
    assert user.email.endswith("@deleted.invalid") and user.status == "deleted"
    members = owner.get(f"/api/v1/organisations/{owner.org_id}/members").json()
    assert [m["email"] for m in members] == ["owner@acme.example.com"]
