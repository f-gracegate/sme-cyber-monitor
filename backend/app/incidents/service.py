"""Incidents, their timeline, alert correlation, and remediation task lifecycle.

Correlation rules (run whenever an alert is raised):

1. If the alert's asset already has an open incident, the alert joins that incident.
2. A critical alert opens a new incident.
3. Three or more high/critical alerts on one asset within 24 hours open a new incident that
   groups them.

Incidents never close themselves: a person confirms the resolution and gives a closure reason.
Remediation tasks linked to a finding are verified automatically when monitoring confirms the
finding has cleared.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import system_context
from app.models import (
    Alert,
    Asset,
    Finding,
    Incident,
    IncidentAlert,
    IncidentAsset,
    IncidentEvent,
    Membership,
    Notification,
    NotificationPreference,
    RemediationTask,
    User,
)
from app.monitoring.catalogue import severity_rank
from app.security.rbac import Perm, permissions_for

OPEN_STATUSES = ("open", "investigating", "contained")
CATEGORIES = (
    "malware",
    "phishing",
    "account_compromise",
    "unauthorised_access",
    "intrusion",
    "data_loss",
    "availability",
    "lost_device",
    "policy_violation",
    "other",
)
RULE_CATEGORY = {
    "malware_detected": "malware",
    "login_after_failed_attempts": "account_compromise",
    "repeated_failed_logins": "unauthorised_access",
    "network_admin_bruteforce": "unauthorised_access",
    "privileged_account_created": "unauthorised_access",
    "network_intrusion_alert": "intrusion",
    "suspicious_process": "intrusion",
    "port_scan_detected": "intrusion",
    "website_unreachable": "availability",
    "website_server_error": "availability",
    "network_device_unreachable": "availability",
    "tls_certificate_expired": "availability",
    "protection_tampering": "policy_violation",
    "security_log_cleared": "intrusion",
}
DUE_IN = {
    "critical": timedelta(days=1),
    "high": timedelta(days=7),
    "medium": timedelta(days=30),
    "low": timedelta(days=90),
}
BURST_WINDOW = timedelta(hours=24)
BURST_SIZE = 3


class Mail:
    """An email to send after the transaction commits (avoids importing the engine's type)."""

    def __init__(self, to: str, subject: str, body: str) -> None:
        self.to, self.subject, self.body = to, subject, body


def add_event(
    db: Session,
    incident: Incident,
    event_type: str,
    *,
    actor: User | None = None,
    actor_label: str | None = None,
    body: str | None = None,
    data: dict | None = None,
) -> IncidentEvent:
    event = IncidentEvent(
        organisation_id=incident.organisation_id,
        incident_id=incident.id,
        event_type=event_type,
        actor_id=actor.id if actor else None,
        actor_label=actor_label or ((actor.full_name or actor.email) if actor else "System"),
        body=body,
        data=data or {},
        occurred_at=datetime.now(UTC),
    )
    db.add(event)
    incident.updated_at = event.occurred_at
    return event


def _responders(db: Session, org_id: uuid.UUID):
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
    return [(u, pref) for u, role, pref in rows if Perm.INCIDENTS_MANAGE in permissions_for(role)]


def notify(
    db: Session, incident: Incident, title: str, body: str, users: list[User] | None = None
) -> list[Mail]:
    """Tell responders (or the given users) about an incident. Returns emails to send."""
    recipients = (
        [(u, None) for u in users]
        if users is not None
        else _responders(db, incident.organisation_id)
    )
    mails = []
    link = f"/incidents/{incident.id}"
    rank = severity_rank(incident.severity)
    for user, pref in recipients:
        in_app_min = pref.in_app_min_severity if pref else "low"
        if in_app_min == "off" or rank < severity_rank(in_app_min):
            continue  # this person asked not to see incidents this minor
        with system_context(db):
            db.add(
                Notification(
                    organisation_id=incident.organisation_id,
                    user_id=user.id,
                    severity=incident.severity,
                    title=title[:200],
                    body=body[:1000],
                    link=link,
                )
            )
            db.flush()
        email_min = pref.email_min_severity if pref else "high"
        if email_min != "off" and rank >= severity_rank(email_min):
            mails.append(
                Mail(
                    user.email,
                    f"[{incident.reference}] {title}",
                    f"{body}\n\nOpen the incident: {settings.web_base_url}{link}",
                )
            )
    return mails


def next_number(db: Session, org_id: uuid.UUID) -> int:
    current = db.scalar(select(func.max(Incident.number)).where(Incident.organisation_id == org_id))
    return (current or 0) + 1


def link_asset(
    db: Session,
    incident: Incident,
    asset_id: uuid.UUID,
    actor: User | None = None,
    quiet: bool = False,
) -> bool:
    exists = db.get(IncidentAsset, (incident.id, asset_id))
    if exists:
        return False
    db.add(
        IncidentAsset(
            incident_id=incident.id, asset_id=asset_id, organisation_id=incident.organisation_id
        )
    )
    db.flush()  # so a second link in the same transaction sees this one
    if not quiet:
        asset = db.get(Asset, asset_id)
        add_event(
            db,
            incident,
            "asset_linked",
            actor=actor,
            body=f"Affected asset added: {asset.name if asset else asset_id}",
            data={"asset_id": str(asset_id)},
        )
    return True


def link_alert(db: Session, incident: Incident, alert: Alert, actor: User | None = None) -> bool:
    if db.get(IncidentAlert, (incident.id, alert.id)):
        return False
    db.add(
        IncidentAlert(
            incident_id=incident.id, alert_id=alert.id, organisation_id=incident.organisation_id
        )
    )
    db.flush()
    link_asset(db, incident, alert.asset_id, actor, quiet=True)
    add_event(
        db,
        incident,
        "alert_linked",
        actor=actor,
        body=f"Alert linked: {alert.title}",
        data={"alert_id": str(alert.id), "severity": alert.severity},
    )
    if severity_rank(alert.severity) > severity_rank(incident.severity):
        previous = incident.severity
        incident.severity = alert.severity
        add_event(
            db,
            incident,
            "severity_changed",
            actor=actor,
            body=f"Severity raised from {previous} to {alert.severity} by a linked alert.",
            data={"from": previous, "to": alert.severity},
        )
    return True


def create_incident(
    db: Session,
    org_id: uuid.UUID,
    *,
    title: str,
    summary: str = "",
    severity: str = "medium",
    category: str = "other",
    source: str = "manual",
    actor: User | None = None,
    owner_id: uuid.UUID | None = None,
    asset_ids: list[uuid.UUID] = (),
    alerts: list[Alert] = (),
) -> tuple[Incident, list[Mail]]:
    incident = Incident(
        organisation_id=org_id,
        number=next_number(db, org_id),
        title=title[:200],
        summary=summary,
        severity=severity,
        category=category,
        source=source,
        owner_id=owner_id,
        reported_by=actor.id if actor else None,
    )
    db.add(incident)
    db.flush()
    origin = {"employee_report": "Reported by", "manual": "Opened by"}.get(source)
    add_event(
        db,
        incident,
        "created",
        actor=actor,
        actor_label=None if actor else "Correlation engine",
        body=f"{origin} {actor.full_name or actor.email}"
        if actor and origin
        else "Opened automatically from correlated alerts",
        data={"source": source, "severity": severity},
    )
    for asset_id in asset_ids:
        link_asset(db, incident, asset_id, actor, quiet=True)
    for alert in alerts:
        link_alert(db, incident, alert, actor)
    db.flush()
    mails = notify(
        db,
        incident,
        f"New {incident.severity} incident: {incident.title}",
        incident.summary or "A new incident needs attention.",
    )
    return incident, mails


def correlate_alert(db: Session, alert: Alert, asset: Asset) -> list[Mail]:
    """Apply the correlation rules to a newly raised alert."""
    existing = db.scalar(
        select(Incident)
        .join(IncidentAsset, IncidentAsset.incident_id == Incident.id)
        .where(IncidentAsset.asset_id == asset.id, Incident.status.in_(OPEN_STATUSES))
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        link_alert(db, existing, alert)
        return []
    finding = db.get(Finding, alert.finding_id)
    category = RULE_CATEGORY.get(finding.rule_key if finding else "", "other")
    if alert.severity == "critical":
        _, mails = create_incident(
            db,
            alert.organisation_id,
            title=f"{alert.title} on {asset.name}",
            summary=finding.description if finding else "",
            severity="critical",
            category=category,
            source="correlation",
            asset_ids=[asset.id],
            alerts=[alert],
        )
        return mails
    if alert.severity == "high":
        recent = list(
            db.scalars(
                select(Alert).where(
                    Alert.asset_id == asset.id,
                    Alert.severity.in_(("high", "critical")),
                    Alert.first_seen_at >= alert.first_seen_at - BURST_WINDOW,
                )
            )
        )
        if len(recent) >= BURST_SIZE:
            _, mails = create_incident(
                db,
                alert.organisation_id,
                title=f"Multiple high-severity alerts on {asset.name}",
                summary=f"{len(recent)} high-severity alerts were raised on {asset.name} within "
                "24 hours. Together they may indicate an attack in progress.",
                severity="high",
                category=category,
                source="correlation",
                asset_ids=[asset.id],
                alerts=recent,
            )
            return mails
    return []


# --- Remediation ---------------------------------------------------------------------------


def default_due(priority: str, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + DUE_IN.get(priority, DUE_IN["medium"])


def verify_tasks_for_finding(
    db: Session, finding: Finding, how: str, actor: User | None = None
) -> int:
    """A finding was resolved: close the remediation tasks attached to it."""
    now = datetime.now(UTC)
    tasks = list(
        db.scalars(
            select(RemediationTask).where(
                RemediationTask.finding_id == finding.id,
                RemediationTask.status.in_(("open", "in_progress", "done")),
            )
        )
    )
    reason = "monitoring confirmed the fix" if how == "monitoring" else "marked fixed"
    for task in tasks:
        task.status = "verified"
        task.verified_at = now
        task.verification = how
        task.completed_at = task.completed_at or now
        if task.incident_id:
            incident = db.get(Incident, task.incident_id)
            add_event(
                db,
                incident,
                "task_updated",
                actor=actor,
                body=f"Task verified ({reason}): {task.title}",
                data={"task_id": str(task.id), "status": "verified"},
            )
    return len(tasks)


def cancel_tasks_for_asset(db: Session, asset_id: uuid.UUID, note: str) -> None:
    for task in db.scalars(
        select(RemediationTask).where(
            RemediationTask.asset_id == asset_id,
            RemediationTask.status.in_(("open", "in_progress")),
        )
    ):
        task.status = "cancelled"
        task.note = note


def cancel_tasks_for_finding(db: Session, finding: Finding, note: str) -> None:
    for task in db.scalars(
        select(RemediationTask).where(
            RemediationTask.finding_id == finding.id,
            RemediationTask.status.in_(("open", "in_progress", "done")),
        )
    ):
        task.status = "cancelled"
        task.note = note
