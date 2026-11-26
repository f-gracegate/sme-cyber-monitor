"""Turns check results into findings, alerts and notifications.

Lifecycle:
  issue detected  → finding opened (or re-opened) → one alert raised → people notified
  seen again      → finding/alert occurrence counters go up (no duplicate alerts)
  no longer seen  → finding and its alert resolved automatically (only after a successful run)
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import (
    Alert,
    Asset,
    CheckRun,
    Finding,
    Membership,
    MonitoringCheck,
    Notification,
    NotificationPreference,
    User,
)
from app.monitoring import checks
from app.monitoring.catalogue import RULES, SEVERITY_SCORE, rules_for, severity_rank
from app.monitoring.scoring import record_snapshot
from app.security.rbac import Perm, permissions_for
from app.services.email import send_email
from app.services.verification import asset_hostname

log = logging.getLogger("app.monitoring")

# (check type, interval in minutes) created automatically when an asset is authorised.
DEFAULT_CHECKS: dict[str, list[tuple[str, int]]] = {
    "website": [("uptime", 5), ("tls", 720), ("security_headers", 360)],
    "domain": [("dns", 60), ("email_security", 720)],
}
ALLOWED_INTERVALS = (5, 15, 30, 60, 180, 360, 720, 1440)
RUNNABLE_ASSET_STATES = ("authorised", "monitoring", "degraded")


@dataclass
class EmailJob:
    to: str
    subject: str
    body: str


def ensure_default_checks(db: Session, asset: Asset) -> list[MonitoringCheck]:
    existing = set(
        db.scalars(select(MonitoringCheck.check_type).where(MonitoringCheck.asset_id == asset.id))
    )
    created = []
    for check_type, interval in DEFAULT_CHECKS.get(asset.type, []):
        if check_type in existing:
            continue
        check = MonitoringCheck(
            organisation_id=asset.organisation_id,
            asset_id=asset.id,
            check_type=check_type,
            interval_minutes=interval,
            next_run_at=datetime.now(UTC),
        )
        db.add(check)
        created.append(check)
    return created


def resolve_asset_findings(db: Session, asset: Asset, note: str, actor_id=None) -> int:
    """Close every open finding and alert for an asset (archived, or its address changed)."""
    now = datetime.now(UTC)
    findings = list(
        db.scalars(
            select(Finding).where(Finding.asset_id == asset.id, Finding.status != "resolved")
        )
    )
    for f in findings:
        f.status, f.resolved_at, f.resolved_by, f.resolution_note = "resolved", now, actor_id, note
    for a in db.scalars(
        select(Alert).where(Alert.asset_id == asset.id, Alert.status != "resolved")
    ):
        a.status, a.resolved_at, a.resolved_by, a.resolution_note = "resolved", now, actor_id, note
    return len(findings)


def collect(check, asset) -> checks.Outcome:
    """Run the network part of a check. Takes plain values, never live ORM objects."""
    try:
        if check.check_type == "uptime":
            return checks.run_uptime(asset.identifier, check.consecutive_failures)
        if check.check_type == "tls":
            return checks.run_tls(asset.identifier)
        if check.check_type == "security_headers":
            return checks.run_security_headers(asset.identifier)
        if check.check_type == "dns":
            return checks.run_dns(asset_hostname(asset), (check.state or {}).get("ns"))
        if check.check_type == "email_security":
            return checks.run_email_security(asset_hostname(asset))
        return checks.Outcome("error", f"Unknown check type {check.check_type}")
    except Exception:  # noqa: BLE001 - a broken check must never stop the worker
        log.exception("check %s failed unexpectedly", check.id)
        return checks.Outcome("error", "Unexpected error while running this check")


def _recipients(db: Session, org_id: uuid.UUID, severity: str):
    rows = db.execute(
        select(User, Membership.role, NotificationPreference)
        .join(Membership, Membership.user_id == User.id)
        .outerjoin(
            NotificationPreference,
            (NotificationPreference.user_id == User.id)
            & (NotificationPreference.organisation_id == org_id),
        )
        .where(
            Membership.organisation_id == org_id,
            Membership.status == "active",
            User.status == "active",
        )
    ).all()
    for user, role, pref in rows:
        if Perm.ALERTS_READ not in permissions_for(role):
            continue
        in_app_min = pref.in_app_min_severity if pref else "low"
        email_min = pref.email_min_severity if pref else "high"
        in_app = in_app_min != "off" and severity_rank(severity) >= severity_rank(in_app_min)
        email = email_min != "off" and severity_rank(severity) >= severity_rank(email_min)
        if in_app or email:
            yield user, in_app, email


def _raise_alert(db: Session, finding: Finding, asset: Asset, now: datetime) -> list[EmailJob]:
    alert = Alert(
        organisation_id=finding.organisation_id,
        asset_id=finding.asset_id,
        finding_id=finding.id,
        title=finding.title,
        severity=finding.severity,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(alert)
    db.flush()
    emails = []
    link = f"/alerts/{alert.id}"
    body = f"{asset.name} ({asset.identifier}): {finding.description}"
    for user, in_app, email in _recipients(db, finding.organisation_id, finding.severity):
        if in_app:
            db.add(
                Notification(
                    organisation_id=finding.organisation_id,
                    user_id=user.id,
                    alert_id=alert.id,
                    severity=finding.severity,
                    title=finding.title,
                    body=body[:1000],
                    link=link,
                    emailed=email,
                )
            )
        if email:
            emails.append(
                EmailJob(
                    user.email,
                    f"[{finding.severity.upper()}] {finding.title} · {asset.name}",
                    f"{body}\n\nWhy it matters: {finding.impact}\n\nWhat to do: "
                    f"{finding.recommendation}\n\nView the alert: {settings.web_base_url}{link}\n\n"
                    "You can change which alerts you receive by email in Settings → Notifications.",
                )
            )
    return emails


def apply_outcome(
    db: Session,
    check: MonitoringCheck,
    asset: Asset,
    outcome: checks.Outcome,
    started: datetime,
    completed: datetime,
) -> list[EmailJob]:
    """Persist one check result. Caller commits."""
    emails: list[EmailJob] = []
    db.add(
        CheckRun(
            organisation_id=check.organisation_id,
            asset_id=asset.id,
            check_id=check.id,
            check_type=check.check_type,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            status=outcome.status,
            summary=outcome.summary[:400],
            result=outcome.data,
        )
    )
    check.last_run_at = completed
    check.last_status = outcome.status
    check.last_summary = outcome.summary[:400]
    check.consecutive_failures = (
        check.consecutive_failures + 1 if outcome.status == "failing" else 0
    )
    if check.check_type == "dns" and outcome.evaluated and outcome.data.get("ns"):
        check.state = {**(check.state or {}), "ns": outcome.data["ns"]}

    if outcome.reachable:
        asset.last_seen_at = completed
    if outcome.status in {"ok", "warning"}:
        asset.last_successful_check_at = completed

    seen: set[str] = set()
    for issue in outcome.issues:
        rule = RULES[issue.rule_key]
        seen.add(rule.key)
        finding = db.scalar(
            select(Finding).where(Finding.asset_id == asset.id, Finding.rule_key == rule.key)
        )
        should_alert = False
        if finding is None:
            finding = Finding(
                organisation_id=asset.organisation_id,
                asset_id=asset.id,
                check_type=rule.check_type,
                rule_key=rule.key,
                title=rule.title,
                description=rule.description,
                impact=rule.impact,
                recommendation=rule.recommendation,
                severity=rule.severity,
                score=SEVERITY_SCORE[rule.severity],
                status="open",
                evidence=issue.evidence,
                first_seen_at=completed,
                last_seen_at=completed,
            )
            db.add(finding)
            db.flush()
            should_alert = True
        else:
            finding.last_seen_at = completed
            finding.occurrences += 1
            finding.evidence = issue.evidence
            if finding.status == "resolved":
                finding.status = "open"
                finding.resolved_at = finding.resolved_by = finding.resolution_note = None
                should_alert = True
        if finding.status != "open":
            continue  # accepted risk: keep tracking, don't alert
        alert = db.scalar(
            select(Alert).where(Alert.finding_id == finding.id, Alert.status != "resolved")
        )
        if alert is not None:
            alert.occurrences += 1
            alert.last_seen_at = completed
        elif should_alert and rule.severity != "informational":
            emails += _raise_alert(db, finding, asset, completed)

    if outcome.evaluated:
        stale = rules_for(check.check_type) - seen
        for finding in db.scalars(
            select(Finding).where(
                Finding.asset_id == asset.id,
                Finding.rule_key.in_(stale),
                Finding.status.in_(("open", "accepted_risk")),
            )
        ):
            if RULES[finding.rule_key].sticky:
                continue
            finding.status = "resolved"
            finding.resolved_at = completed
            finding.resolved_by = None
            finding.resolution_note = "Automatically resolved: no longer detected."
            for alert in db.scalars(
                select(Alert).where(Alert.finding_id == finding.id, Alert.status != "resolved")
            ):
                alert.status = "resolved"
                alert.resolved_at = completed
                alert.resolution_note = "Automatically resolved: the condition cleared."

    db.flush()
    _refresh_asset(db, asset)
    record_snapshot(db, asset.organisation_id)
    return emails


def _refresh_asset(db: Session, asset: Asset) -> None:
    if asset.monitoring_status in RUNNABLE_ASSET_STATES:
        statuses = set(
            db.scalars(
                select(MonitoringCheck.last_status).where(
                    MonitoringCheck.asset_id == asset.id, MonitoringCheck.enabled.is_(True)
                )
            )
        )
        asset.monitoring_status = "degraded" if "error" in statuses else "monitoring"
    open_sev = list(
        db.scalars(
            select(Finding.severity).where(Finding.asset_id == asset.id, Finding.status == "open")
        )
    )
    ranked = [s for s in open_sev if s != "informational"]
    if ranked:
        asset.risk_level = max(ranked, key=severity_rank)
    elif asset.last_successful_check_at:
        asset.risk_level = "low"


def execute_check(check_id: uuid.UUID) -> str | None:
    """Run one check end to end in its own sessions. Network I/O happens outside transactions."""
    db = SessionLocal()
    # Workers are trusted system code: they read across tenants, and every row they write takes
    # its organisation from the check record, never from what the network returned.
    db.info["rls"] = {"bypass": True}
    try:
        check = db.get(MonitoringCheck, check_id)
        asset = db.get(Asset, check.asset_id) if check else None
        if (
            check is None
            or asset is None
            or not check.enabled
            or asset.status != "active"
            or asset.monitoring_status not in RUNNABLE_ASSET_STATES
        ):
            return None
        # Copy what the check needs, then end the transaction: no DB locks during network calls.
        check_view = SimpleNamespace(
            id=check.id,
            check_type=check.check_type,
            consecutive_failures=check.consecutive_failures,
            state=dict(check.state or {}),
        )
        asset_view = SimpleNamespace(type=asset.type, identifier=asset.identifier)
        db.rollback()
        started = datetime.now(UTC)
        outcome = collect(check_view, asset_view)
        completed = datetime.now(UTC)
        check = db.get(MonitoringCheck, check_id)
        asset = db.get(Asset, check.asset_id)
        emails = apply_outcome(db, check, asset, outcome, started, completed)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("failed to record result for check %s", check_id)
        return None
    finally:
        db.close()
    for job in emails:
        send_email(job.to, job.subject, job.body)
    return outcome.status


def next_run_time(check: MonitoringCheck, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(minutes=check.interval_minutes)
