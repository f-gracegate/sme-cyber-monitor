import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.models import Alert, Asset, Finding, MonitoringCheck, Notification
from app.monitoring import checks, engine
from app.services import verification
from app.services.email import read_dev_mailbox
from app.workers import monitor
from tests.conftest import create_org, invite_and_join, register


def authorised_website(api, monkeypatch, identifier="shop.example.com") -> dict:
    asset = api.post(
        "/api/v1/assets", {"name": "Shop", "type": "website", "identifier": identifier}
    ).json()
    api.post(f"/api/v1/assets/{asset['id']}/verification", {"method": "dns_txt"})
    monkeypatch.setattr(
        verification,
        "check_dns_txt",
        lambda host, ch: verification.CheckResult(True, "matched", {}),
    )
    detail = api.post(f"/api/v1/assets/{asset['id']}/verify").json()
    assert detail["monitoring_status"] == "authorised"
    return detail


@pytest.fixture
def system_db():
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    yield db
    db.close()


def run(db, check_type: str, asset_id: str, outcome: checks.Outcome):
    check = db.scalar(
        select(MonitoringCheck).where(
            MonitoringCheck.asset_id == uuid.UUID(asset_id),
            MonitoringCheck.check_type == check_type,
        )
    )
    asset = db.get(Asset, check.asset_id)
    now = datetime.now(UTC)
    emails = engine.apply_outcome(db, check, asset, outcome, now, now + timedelta(seconds=1))
    db.commit()
    return emails


def bad_headers():
    return checks.Outcome(
        "warning",
        "issues",
        issues=[checks.Issue("missing_hsts"), checks.Issue("missing_csp")],
        reachable=True,
    )


def test_verifying_a_website_creates_default_checks(owner, monkeypatch):
    asset = authorised_website(owner, monkeypatch)
    checks_ = owner.get("/api/v1/monitoring/checks", params={"asset_id": asset["id"]}).json()
    assert {c["check_type"] for c in checks_} == {"uptime", "tls", "security_headers"}
    assert all(c["last_status"] == "pending" for c in checks_)


def test_findings_alerts_and_notifications_lifecycle(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    analyst = invite_and_join(owner, "analyst@acme.example.com", "security_analyst")

    emails = run(system_db, "security_headers", asset["id"], bad_headers())
    findings = owner.get("/api/v1/findings").json()
    assert {f["rule_key"] for f in findings["items"]} == {"missing_hsts", "missing_csp"}
    alerts = owner.get("/api/v1/alerts").json()["items"]
    assert len(alerts) == 2 and all(a["status"] == "new" for a in alerts)
    # Medium/low alerts notify in-app; email defaults to high and above.
    assert emails == []
    assert analyst.get("/api/v1/notifications").json()["unread"] == 2

    # Seen again: counted, not duplicated.
    run(system_db, "security_headers", asset["id"], bad_headers())
    alerts = owner.get("/api/v1/alerts").json()["items"]
    assert len(alerts) == 2 and all(a["occurrences"] == 2 for a in alerts)

    # A clean run resolves both the findings and the alerts automatically.
    run(system_db, "security_headers", asset["id"], checks.Outcome("ok", "fine", reachable=True))
    assert owner.get("/api/v1/findings").json()["total"] == 0
    assert owner.get("/api/v1/alerts").json()["total"] == 0
    resolved = owner.get("/api/v1/alerts", params={"status": "resolved"}).json()["items"]
    assert all("Automatically resolved" in a["resolution_note"] for a in resolved)

    # It comes back: the finding re-opens and a fresh alert is raised.
    run(system_db, "security_headers", asset["id"], bad_headers())
    assert owner.get("/api/v1/alerts").json()["total"] == 2


def test_high_severity_alerts_are_emailed(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    emails = run(
        system_db,
        "tls",
        asset["id"],
        checks.Outcome(
            "warning", "expired", issues=[checks.Issue("tls_certificate_expired")], reachable=True
        ),
    )
    assert [e.to for e in emails] == ["owner@acme.example.com"]
    engine.send_email(emails[0].to, emails[0].subject, emails[0].body)
    assert any("TLS certificate has expired" in m["subject"] for m in read_dev_mailbox())


def test_failed_checks_never_clear_findings(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    run(
        system_db,
        "security_headers",
        asset["id"],
        checks.Outcome("error", "Could not load the website"),
    )
    assert owner.get("/api/v1/findings").json()["total"] == 2
    detail = owner.get(f"/api/v1/assets/{asset['id']}").json()
    assert detail["monitoring_status"] == "degraded"


def test_sticky_findings_wait_for_a_person(owner, monkeypatch, system_db):
    domain = owner.post(
        "/api/v1/assets", {"name": "Domain", "type": "domain", "identifier": "acme.example.com"}
    ).json()
    owner.post(f"/api/v1/assets/{domain['id']}/verification", {"method": "dns_txt"})
    monkeypatch.setattr(
        verification,
        "check_dns_txt",
        lambda host, ch: verification.CheckResult(True, "matched", {}),
    )
    owner.post(f"/api/v1/assets/{domain['id']}/verify")
    changed = checks.Outcome(
        "warning",
        "ns changed",
        issues=[checks.Issue("nameservers_changed", {"previous": ["a"], "current": ["b"]})],
        reachable=True,
    )
    run(system_db, "dns", domain["id"], changed)
    run(system_db, "dns", domain["id"], checks.Outcome("ok", "fine", reachable=True))
    open_ = owner.get("/api/v1/findings").json()["items"]
    assert [f["rule_key"] for f in open_] == ["nameservers_changed"]


def test_accepted_risk_is_tracked_without_new_alerts(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    finding = next(
        f for f in owner.get("/api/v1/findings").json()["items"] if f["rule_key"] == "missing_csp"
    )
    r = owner.patch(f"/api/v1/findings/{finding['id']}", {"status": "accepted_risk"})
    assert r.status_code == 422  # a reason is required
    r = owner.patch(
        f"/api/v1/findings/{finding['id']}",
        {"status": "accepted_risk", "note": "Legacy plugin; replacing next quarter"},
    )
    assert r.json()["status"] == "accepted_risk" and r.json()["open_alert_id"] is None
    run(system_db, "security_headers", asset["id"], bad_headers())
    alerts = owner.get("/api/v1/alerts").json()["items"]
    assert [a["title"] for a in alerts] == ["HSTS is not enabled"]


def test_posture_score_only_exists_with_data(owner, monkeypatch, system_db):
    assert owner.get("/api/v1/overview").json()["posture_score"] is None
    asset = authorised_website(owner, monkeypatch)
    run(
        system_db,
        "tls",
        asset["id"],
        checks.Outcome(
            "warning", "x", issues=[checks.Issue("tls_certificate_expiring_14d")], reachable=True
        ),
    )
    data = owner.get("/api/v1/overview").json()
    assert data["posture_score"] == 85
    assert data["findings_open_by_severity"]["high"] == 1
    assert data["trend"][-1]["score"] == 85
    assert data["most_exposed_assets"][0]["name"] == "Shop"


def test_alert_workflow_and_permissions(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(
        system_db,
        "tls",
        asset["id"],
        checks.Outcome(
            "warning", "x", issues=[checks.Issue("tls_certificate_invalid")], reachable=True
        ),
    )
    alert = owner.get("/api/v1/alerts").json()["items"][0]
    employee = invite_and_join(owner, "staff@acme.example.com", "employee")
    auditor = invite_and_join(owner, "audit@acme.example.com", "auditor")
    assert employee.get("/api/v1/alerts").status_code == 403
    assert auditor.get(f"/api/v1/alerts/{alert['id']}").status_code == 200
    assert (
        auditor.patch(f"/api/v1/alerts/{alert['id']}", {"status": "acknowledged"}).status_code
        == 403
    )

    r = owner.patch(f"/api/v1/alerts/{alert['id']}", {"status": "investigating"})
    assert r.json()["status"] == "investigating" and r.json()["acknowledged_at"]
    assert r.json()["finding"]["recommendation"]
    r = owner.patch(f"/api/v1/alerts/{alert['id']}", {"status": "resolved", "note": "Fixed chain"})
    assert r.json()["resolved_by_name"] == "Ama Owner"
    assert owner.patch(f"/api/v1/alerts/{alert['id']}", {"status": "new"}).status_code == 409


def test_monitoring_data_is_isolated_between_organisations(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    finding = owner.get("/api/v1/findings").json()["items"][0]
    alert = owner.get("/api/v1/alerts").json()["items"][0]
    check = owner.get("/api/v1/monitoring/checks").json()[0]

    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get("/api/v1/findings").json()["total"] == 0
    assert other.get(f"/api/v1/findings/{finding['id']}").status_code == 404
    assert other.get(f"/api/v1/alerts/{alert['id']}").status_code == 404
    assert other.patch(f"/api/v1/alerts/{alert['id']}", {"status": "resolved"}).status_code == 404
    assert other.post(f"/api/v1/monitoring/checks/{check['id']}/run").status_code == 404
    assert other.get("/api/v1/notifications").json()["unread"] == 0


def test_notifications_are_personal(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    analyst = invite_and_join(owner, "a2@acme.example.com", "security_analyst")
    run(system_db, "security_headers", asset["id"], bad_headers())
    mine = owner.get("/api/v1/notifications").json()
    assert mine["unread"] == 2
    owner.post("/api/v1/notifications/read", {})
    assert owner.get("/api/v1/notifications").json()["unread"] == 0
    assert analyst.get("/api/v1/notifications").json()["unread"] == 2
    # Row-Level Security: even an unfiltered query only returns the current user's rows.
    db = SessionLocal()
    db.info["rls"] = {"org": owner.org_id, "user": str(uuid.uuid4())}
    assert db.scalars(select(Notification)).all() == []
    db.close()


def test_preferences_control_email(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    r = owner.client.put(
        "/api/v1/notifications/preferences",
        json={"email_min_severity": "off", "in_app_min_severity": "high"},
        headers=owner._headers(),
    )
    assert r.status_code == 200
    emails = run(
        system_db,
        "tls",
        asset["id"],
        checks.Outcome(
            "warning",
            "x",
            issues=[checks.Issue("tls_certificate_expired"), checks.Issue("tls_legacy_protocol")],
            reachable=True,
        ),
    )
    assert emails == []
    assert owner.get("/api/v1/notifications").json()["unread"] == 1  # medium filtered out


def test_worker_claims_only_due_checks_of_authorised_assets(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    pending = owner.post(
        "/api/v1/assets",
        {"name": "Unverified", "type": "website", "identifier": "other.example.com"},
    ).json()
    system_db.add(
        MonitoringCheck(
            organisation_id=uuid.UUID(owner.org_id),
            asset_id=uuid.UUID(pending["id"]),
            check_type="uptime",
            interval_minutes=5,
        )
    )
    system_db.commit()
    claimed = monitor.claim_due(limit=50)
    claimed_assets = set(
        system_db.scalars(select(MonitoringCheck.asset_id).where(MonitoringCheck.id.in_(claimed)))
    )
    assert claimed_assets == {uuid.UUID(asset["id"])}
    assert monitor.claim_due(limit=50) == []  # already pushed to their next interval

    check = owner.get("/api/v1/monitoring/checks", params={"asset_id": asset["id"]}).json()[0]
    assert owner.post(f"/api/v1/monitoring/checks/{check['id']}/run").status_code == 200
    assert monitor.claim_due(limit=50) == [uuid.UUID(check["id"])]


def test_execute_check_end_to_end(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    monkeypatch.setattr(
        checks,
        "run_uptime",
        lambda url, failures: checks.Outcome(
            "ok", "Up · HTTP 200 in 80 ms", {"status_code": 200}, reachable=True
        ),
    )
    check_id = system_db.scalar(
        select(MonitoringCheck.id).where(
            MonitoringCheck.asset_id == uuid.UUID(asset["id"]),
            MonitoringCheck.check_type == "uptime",
        )
    )
    assert engine.execute_check(check_id) == "ok"
    runs = owner.get("/api/v1/monitoring/runs", params={"asset_id": asset["id"]}).json()
    assert runs["total"] == 1 and runs["items"][0]["summary"].startswith("Up")
    detail = owner.get(f"/api/v1/assets/{asset['id']}").json()
    assert detail["monitoring_status"] == "monitoring" and detail["last_seen_at"]


def test_archiving_resolves_open_findings(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    owner.post(f"/api/v1/assets/{asset['id']}/archive")
    system_db.expire_all()
    statuses = set(system_db.scalars(select(Finding.status)))
    assert statuses == {"resolved"}
    assert set(system_db.scalars(select(Alert.status))) == {"resolved"}
    system_db.execute(update(MonitoringCheck).values(next_run_at=datetime.now(UTC)))
    system_db.commit()
    assert monitor.claim_due() == []  # archived assets are not checked
