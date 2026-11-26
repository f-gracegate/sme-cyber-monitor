import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import ProgrammingError

from app.core.config import settings
from app.core.db import SessionLocal, set_tenant_context
from app.models import IncidentEvidence, RemediationTask, Report, Subscription
from app.monitoring import checks
from app.reports.service import generate_monthly_reports
from app.services.email import read_dev_mailbox
from tests.conftest import create_org, invite_and_join, register
from tests.test_monitoring_engine import authorised_website, bad_headers, run


@pytest.fixture
def system_db():
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    yield db
    db.close()


@pytest.fixture
def roomy(owner):
    """More team members than the Starter plan allows."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(Subscription).values(plan_code="professional"))
    db.commit()
    db.close()
    return owner


def critical(db, asset_id, rule="tls_certificate_expired"):
    run(
        db,
        "tls",
        asset_id,
        checks.Outcome("warning", "x", issues=[checks.Issue(rule)], reachable=True),
    )


# --- Correlation ---------------------------------------------------------------------------


def test_critical_alert_opens_an_incident_and_later_alerts_join_it(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    critical(system_db, asset["id"])
    incidents = owner.get("/api/v1/incidents").json()["items"]
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["reference"] == "INC-0001" and inc["severity"] == "critical"
    assert inc["source"] == "correlation" and inc["alert_count"] == 1
    assert inc["category"] == "availability"

    run(system_db, "security_headers", asset["id"], bad_headers())
    detail = owner.get(f"/api/v1/incidents/{inc['id']}").json()
    assert len(detail["alerts"]) == 3  # the critical one plus two from headers
    assert owner.get("/api/v1/incidents").json()["total"] == 1
    kinds = [e["event_type"] for e in detail["timeline"]]
    assert kinds.count("alert_linked") == 3 and kinds[-1] == "created"


def test_a_burst_of_high_alerts_opens_an_incident(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    for rule in ("tls_certificate_expiring_14d", "tls_certificate_invalid"):
        run(
            system_db,
            "tls",
            asset["id"],
            checks.Outcome("warning", "x", issues=[checks.Issue(rule)], reachable=True),
        )
    assert owner.get("/api/v1/incidents").json()["total"] == 0  # two isn't a pattern yet
    run(
        system_db,
        "uptime",
        asset["id"],
        checks.Outcome("failing", "down", issues=[checks.Issue("website_unreachable")]),
    )
    inc = owner.get("/api/v1/incidents").json()["items"][0]
    assert inc["title"].startswith("Multiple high-severity alerts") and inc["alert_count"] == 3


# --- Lifecycle and permissions -------------------------------------------------------------


def test_incident_lifecycle(roomy):
    analyst = invite_and_join(roomy, "analyst@acme.example.com", "security_analyst")
    r = roomy.post(
        "/api/v1/incidents",
        {
            "title": "Phishing email to accounts",
            "summary": "Fake GRA invoice.",
            "category": "phishing",
            "severity": "high",
        },
    )
    assert r.status_code == 201
    inc = r.json()
    me = next(
        m
        for m in roomy.get(f"/api/v1/organisations/{roomy.org_id}/members").json()
        if m["email"] == "analyst@acme.example.com"
    )
    base = f"/api/v1/incidents/{inc['id']}"
    roomy.patch(base, {"owner_id": me["user_id"]})
    assert any(
        "assigned" in n["title"] for n in analyst.get("/api/v1/notifications").json()["items"]
    )
    for status in ("investigating", "contained", "resolved"):
        assert analyst.patch(base, {"status": status}).status_code == 200
    assert analyst.patch(base, {"status": "closed"}).status_code == 422  # reason needed
    r = analyst.patch(
        base,
        {
            "status": "closed",
            "closure_reason": "resolved",
            "resolution_summary": "Blocked sender, reset two passwords.",
        },
    )
    detail = analyst.get(base).json()
    assert detail["status"] == "closed" and detail["closure_reason"] == "resolved"
    assert detail["contained_at"] and detail["closed_at"]
    analyst.patch(base, {"status": "investigating"})
    detail = analyst.get(base).json()
    assert detail["closed_at"] is None and detail["timeline"][0]["event_type"] == "reopened"


def test_employees_report_incidents_but_only_see_their_own(roomy):
    employee = invite_and_join(roomy, "staff@acme.example.com", "employee")
    roomy.post("/api/v1/incidents", {"title": "Internal investigation"})
    r = employee.post(
        "/api/v1/incidents",
        {
            "title": "Suspicious MoMo request",
            "summary": "Someone called asking for a code.",
            "severity": "critical",
            "category": "phishing",
        },
    )
    assert r.status_code == 201
    mine = r.json()
    assert mine["source"] == "employee_report" and mine["severity"] == "medium"
    listed = employee.get("/api/v1/incidents").json()["items"]
    assert [i["id"] for i in listed] == [mine["id"]]
    assert (
        employee.post(
            f"/api/v1/incidents/{mine['id']}/notes", {"body": "They called again."}
        ).status_code
        == 201
    )
    assert (
        employee.patch(f"/api/v1/incidents/{mine['id']}", {"status": "closed"}).status_code == 403
    )
    others = [i for i in roomy.get("/api/v1/incidents").json()["items"] if i["id"] != mine["id"]]
    assert employee.get(f"/api/v1/incidents/{others[0]['id']}").status_code == 404
    assert employee.get("/api/v1/alerts").status_code == 403


def test_incidents_can_be_searched_by_title_or_reference(owner):
    owner.post("/api/v1/incidents", {"title": "Phishing email to finance"})
    second = owner.post("/api/v1/incidents", {"title": "Lost laptop"}).json()

    def found(q):
        return [i["title"] for i in owner.get("/api/v1/incidents", params={"q": q}).json()["items"]]

    assert found("phishing") == ["Phishing email to finance"]
    assert found(second["reference"]) == ["Lost laptop"]
    assert found(second["reference"].lower().replace("-", "")) == ["Lost laptop"]


def test_incident_timeline_is_append_only(owner):
    inc = owner.post("/api/v1/incidents", {"title": "Test"}).json()
    db = SessionLocal()
    db.info["rls"] = {}
    set_tenant_context(db, org=owner.org_id)
    with pytest.raises(ProgrammingError):
        db.execute(text("UPDATE incident_events SET body = 'rewritten'"))
    db.rollback()
    db.close()
    assert owner.get(f"/api/v1/incidents/{inc['id']}").json()["timeline"][0]["body"]


def test_incidents_are_isolated_between_organisations(owner):
    inc = owner.post("/api/v1/incidents", {"title": "Ours"}).json()
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get("/api/v1/incidents").json()["total"] == 0
    assert other.get(f"/api/v1/incidents/{inc['id']}").status_code == 404
    assert other.post(f"/api/v1/incidents/{inc['id']}/notes", {"body": "hi"}).status_code == 404


# --- Evidence ------------------------------------------------------------------------------


def upload(api, incident_id, name, data, ctype="application/octet-stream"):
    headers = api._headers()
    return api.client.post(
        f"/api/v1/incidents/{incident_id}/evidence",
        headers=headers,
        files={"file": (name, io.BytesIO(data), ctype)},
        data={"description": "test"},
    )


def test_evidence_is_encrypted_hashed_and_downloaded_safely(owner, system_db):
    inc = owner.post("/api/v1/incidents", {"title": "Evidence"}).json()
    content = b"From: scam@example.com\nSubject: Urgent invoice\n<script>alert(1)</script>"
    r = upload(owner, inc["id"], "../../phish.eml", content, "message/rfc822")
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["filename"] == "phish.eml" and len(ev["sha256"]) == 64

    stored = system_db.scalar(select(IncidentEvidence))
    raw = (Path(settings.storage_dir) / stored.storage_key).read_bytes()
    assert content not in raw  # encrypted at rest

    dl = owner.get(f"/api/v1/incidents/{inc['id']}/evidence/{ev['id']}")
    assert dl.content == content
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.headers["content-type"] == "application/octet-stream"

    assert upload(owner, inc["id"], "run.exe", b"MZ").status_code == 415
    big = b"x" * (settings.max_evidence_bytes + 1)
    assert upload(owner, inc["id"], "big.log", big).status_code == 413

    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get(f"/api/v1/incidents/{inc['id']}/evidence/{ev['id']}").status_code == 404


# --- Remediation ---------------------------------------------------------------------------


def test_tasks_from_findings_are_verified_by_monitoring(roomy, monkeypatch, system_db):
    asset = authorised_website(roomy, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    finding = next(
        f for f in roomy.get("/api/v1/findings").json()["items"] if f["rule_key"] == "missing_hsts"
    )
    employee = invite_and_join(roomy, "dev@acme.example.com", "employee")
    dev = next(
        m
        for m in roomy.get(f"/api/v1/organisations/{roomy.org_id}/members").json()
        if m["email"] == "dev@acme.example.com"
    )
    r = roomy.post(
        "/api/v1/remediation-tasks", {"finding_id": finding["id"], "assignee_id": dev["user_id"]}
    )
    assert r.status_code == 201
    task = r.json()
    assert task["title"] == "Fix: HSTS is not enabled" and task["priority"] == "medium"
    assert task["description"].startswith("Add 'Strict-Transport-Security")
    due = datetime.fromisoformat(task["due_at"])
    assert timedelta(days=29) < due - datetime.now(UTC) <= timedelta(days=30)

    mine = employee.get("/api/v1/remediation-tasks").json()["items"]
    assert [t["id"] for t in mine] == [task["id"]]
    base = f"/api/v1/remediation-tasks/{task['id']}"
    assert employee.patch(base, {"title": "hack"}).status_code == 403
    assert (
        employee.patch(base, {"status": "done", "note": "Added header"}).json()["status"] == "done"
    )  # awaiting verification: the finding is still open

    run(system_db, "security_headers", asset["id"], checks.Outcome("ok", "fine", reachable=True))
    verified = roomy.get("/api/v1/remediation-tasks", params={"status": "verified"}).json()
    assert verified["items"][0]["verification"] == "monitoring"
    summary = roomy.get("/api/v1/remediation/summary").json()
    assert summary["completed_30d"] == 1 and summary["on_time_rate"] == 100


def test_incident_actions_and_overdue_work_lower_the_score(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "uptime", asset["id"], checks.Outcome("ok", "up", reachable=True))
    before = owner.get("/api/v1/overview").json()["posture_score"]
    inc = owner.post(
        "/api/v1/incidents", {"title": "Compromised mailbox", "severity": "high"}
    ).json()
    task = owner.post(
        "/api/v1/remediation-tasks",
        {
            "incident_id": inc["id"],
            "kind": "containment",
            "title": "Reset mailbox password",
            "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    ).json()
    assert task["overdue"] and task["incident_reference"] == "INC-0001"
    data = owner.get("/api/v1/overview").json()
    assert data["open_incidents"] == 1 and data["overdue_tasks"] == 1
    assert data["posture_components"]["incidents"] == 80
    assert data["posture_components"]["remediation"] == 90
    assert data["posture_score"] < before
    timeline = owner.get(f"/api/v1/incidents/{inc['id']}").json()["timeline"]
    assert timeline[0]["event_type"] == "task_added"


def test_accepting_a_risk_cancels_its_tasks(owner, monkeypatch, system_db):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    finding = owner.get("/api/v1/findings").json()["items"][0]
    owner.post("/api/v1/remediation-tasks", {"finding_id": finding["id"]})
    owner.patch(
        f"/api/v1/findings/{finding['id']}",
        {"status": "accepted_risk", "note": "Compensating control"},
    )
    statuses = set(system_db.scalars(select(RemediationTask.status)))
    assert statuses == {"cancelled"}


# --- Reports -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "report_type",
    [
        "executive",
        "asset_inventory",
        "endpoint_health",
        "findings",
        "incidents",
        "remediation",
        "coverage",
    ],
)
def test_every_report_renders_as_pdf(owner, monkeypatch, system_db, report_type):
    asset = authorised_website(owner, monkeypatch)
    run(system_db, "security_headers", asset["id"], bad_headers())
    owner.post("/api/v1/incidents", {"title": "Test incident"})
    r = owner.post("/api/v1/reports", {"report_type": report_type})
    assert r.status_code == 201, r.text
    pdf = owner.get(f"/api/v1/reports/{r.json()['id']}/download")
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 1500


def test_csv_exports_neutralise_formulas(owner):
    owner.post(
        "/api/v1/assets",
        {"name": '=HYPERLINK("http://evil")', "type": "server", "identifier": "srv"},
    )
    r = owner.post("/api/v1/reports", {"report_type": "asset_inventory", "format": "csv"})
    body = owner.get(f"/api/v1/reports/{r.json()['id']}/download").content.decode("utf-8-sig")
    assert body.startswith("Name,Type,Identifier")
    assert "'=HYPERLINK" in body
    assert (
        owner.post("/api/v1/reports", {"report_type": "executive", "format": "csv"}).status_code
        == 422
    )


def test_reports_are_permissioned_and_isolated(roomy):
    report = roomy.post("/api/v1/reports", {"report_type": "coverage"}).json()
    employee = invite_and_join(roomy, "staff@acme.example.com", "employee")
    assert employee.get("/api/v1/reports").status_code == 403
    auditor = invite_and_join(roomy, "audit@acme.example.com", "auditor")
    assert auditor.get(f"/api/v1/reports/{report['id']}/download").status_code == 200
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get(f"/api/v1/reports/{report['id']}/download").status_code == 404


def test_monthly_executive_reports_are_generated_once(owner, system_db):
    now = datetime(2026, 12, 1, 6, 0, tzinfo=UTC)
    assert generate_monthly_reports(system_db, now) == 1
    assert generate_monthly_reports(system_db, now) == 0
    report = system_db.scalar(select(Report))
    assert report.scheduled and report.period_start == datetime(2026, 11, 1, tzinfo=UTC)
    assert any("November 2026 security report" in m["subject"] for m in read_dev_mailbox())
    listed = owner.get("/api/v1/reports").json()["items"][0]
    assert listed["created_by_name"] == "Monthly schedule"
