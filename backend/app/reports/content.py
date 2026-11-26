"""Report content: the numbers and tables behind each report, independent of file format."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.endpoints.service import is_online
from app.models import (
    Agent,
    Alert,
    Asset,
    Department,
    Finding,
    Incident,
    MonitoringCheck,
    Organisation,
    RemediationTask,
    RiskScoreSnapshot,
    User,
)
from app.monitoring.scoring import compute_posture

REPORT_TYPES = {
    "executive": "Executive security summary",
    "asset_inventory": "Asset inventory",
    "endpoint_health": "Endpoint health",
    "findings": "Vulnerability and configuration findings",
    "incidents": "Incident history",
    "remediation": "Remediation progress",
    "coverage": "Monitoring coverage",
}
CSV_TYPES = {"asset_inventory", "endpoint_health", "findings", "incidents", "remediation"}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
TYPE_LABEL = {
    "website": "Website",
    "domain": "Domain",
    "workstation": "Workstation",
    "laptop": "Laptop",
    "server": "Server",
    "firewall": "Firewall",
    "router": "Router",
    "switch": "Switch",
    "network_device": "Network device",
    "cloud_account": "Cloud account",
    "cloud_service": "Cloud service",
}
COMPONENT_LABEL = {
    "findings": "Open findings",
    "coverage": "Monitoring coverage",
    "endpoint_health": "Device health",
    "remediation": "Fixing on time",
    "incidents": "Open incidents",
}


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    widths: list[float] | None = None


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    table: Table | None = None
    chart: list[tuple[str, int]] | None = None  # (label, value) points for a trend line


@dataclass
class ReportContent:
    title: str
    organisation: str
    period: str
    kpis: list[tuple[str, str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    csv: Table | None = None


def _d(value: datetime | None) -> str:
    return value.strftime("%d %b %Y") if value else "—"


def _name(db: Session, user_id) -> str:
    if not user_id:
        return "Unassigned"
    user = db.get(User, user_id)
    return (user.full_name or user.email) if user else "—"


def build(
    db: Session, org_id: uuid.UUID, report_type: str, start: datetime, end: datetime
) -> ReportContent:
    org = db.get(Organisation, org_id)
    content = ReportContent(
        title=REPORT_TYPES[report_type],
        organisation=org.name,
        period=f"{_d(start)} – {_d(end - timedelta(seconds=1))}",
    )
    BUILDERS[report_type](db, org_id, start, end, content)
    return content


def _active(org_id):
    return (Asset.organisation_id == org_id) & (Asset.status == "active")


def _open_findings(db: Session, org_id) -> list[tuple[Finding, Asset]]:
    rows = db.execute(
        select(Finding, Asset)
        .join(Asset, Asset.id == Finding.asset_id)
        .where(Finding.organisation_id == org_id, Finding.status == "open", _active(org_id))
    ).all()
    return sorted(rows, key=lambda r: (SEV_ORDER.get(r[0].severity, 9), r[0].first_seen_at))


def _executive(db, org_id, start, end, c: ReportContent) -> None:
    posture = compute_posture(db, org_id)
    sev = posture["open_by_severity"]
    urgent = sev["critical"] + sev["high"]
    alerts = (
        db.scalar(
            select(func.count()).where(
                Alert.organisation_id == org_id,
                Alert.first_seen_at >= start,
                Alert.first_seen_at < end,
            )
        )
        or 0
    )
    opened = (
        db.scalar(
            select(func.count()).where(
                Incident.organisation_id == org_id,
                Incident.created_at >= start,
                Incident.created_at < end,
            )
        )
        or 0
    )
    closed = (
        db.scalar(
            select(func.count()).where(
                Incident.organisation_id == org_id,
                Incident.closed_at >= start,
                Incident.closed_at < end,
            )
        )
        or 0
    )
    fixed = (
        db.scalar(
            select(func.count()).where(
                RemediationTask.organisation_id == org_id,
                RemediationTask.status == "verified",
                RemediationTask.verified_at >= start,
                RemediationTask.verified_at < end,
            )
        )
        or 0
    )
    score = posture["score"]
    c.kpis = [
        (
            "Security score",
            "—" if score is None else f"{score}/100",
            f"{posture['confidence']}% of assets monitored",
        ),
        ("Urgent findings", str(urgent), "Critical and high, open now"),
        ("Alerts raised", str(alerts), "During this period"),
        ("Incidents", f"{opened} opened / {closed} closed", "During this period"),
        ("Fixes verified", str(fixed), "During this period"),
    ]
    if score is None:
        verdict = (
            "We can't score your security yet because none of your assets has "
            "monitoring data. Start by verifying your website and installing agents."
        )
    elif score >= 80:
        verdict = f"Your security score is {score} out of 100: a good position to maintain."
    elif score >= 60:
        verdict = (
            f"Your security score is {score} out of 100. There are known weaknesses that "
            "deserve attention this month."
        )
    else:
        verdict = (
            f"Your security score is {score} out of 100. Several serious weaknesses are "
            "open and should be treated as a priority."
        )
    coverage_note = (
        f"The score is based on {posture['monitored_assets']} of "
        f"{posture['monitorable_assets']} assets; unmonitored assets lower it "
        "because we can't see their risks."
    )
    c.sections.append(Section("Summary", paragraphs=[verdict, coverage_note]))
    breakdown = [
        f"{COMPONENT_LABEL[k]}: {v}/100" for k, v in posture["components"].items() if v is not None
    ]
    c.sections.append(Section("What makes up the score", bullets=breakdown))

    trend = list(
        db.scalars(
            select(RiskScoreSnapshot)
            .where(
                RiskScoreSnapshot.organisation_id == org_id,
                RiskScoreSnapshot.day >= start.date(),
                RiskScoreSnapshot.day < end.date() + timedelta(days=1),
            )
            .order_by(RiskScoreSnapshot.day)
        )
    )
    if len(trend) >= 2:
        c.sections.append(
            Section(
                "Score over the period", chart=[(t.day.strftime("%d %b"), t.score) for t in trend]
            )
        )

    top = _open_findings(db, org_id)[:10]
    if top:
        c.sections.append(
            Section(
                "Top risks to fix",
                table=Table(
                    ["Severity", "Issue", "Asset", "Open since"],
                    [
                        [f.severity.capitalize(), f.title, a.name, _d(f.first_seen_at)]
                        for f, a in top
                    ],
                    [0.12, 0.48, 0.25, 0.15],
                ),
            )
        )
    else:
        c.sections.append(
            Section("Top risks to fix", paragraphs=["No open findings on monitored assets."])
        )

    actions = []
    if urgent:
        actions.append(
            f"Fix the {urgent} critical and high findings listed above, starting with the oldest."
        )
    if posture["neglected_findings"]:
        actions.append(
            f"Assign an owner and due date to {posture['neglected_findings']} urgent "
            "finding(s) nobody is working on."
        )
    if posture["overdue_tasks"]:
        actions.append(f"Follow up on {posture['overdue_tasks']} overdue security fix(es).")
    if posture["open_incidents"]:
        actions.append(f"Close out {posture['open_incidents']} open incident(s).")
    if posture["confidence"] < 80:
        actions.append(
            "Increase monitoring coverage: verify websites and install agents on "
            "computers and servers that aren't reporting."
        )
    c.sections.append(
        Section(
            "Recommended next steps",
            bullets=actions or ["Keep monitoring in place and review this report next month."],
        )
    )


def _asset_inventory(db, org_id, start, end, c: ReportContent) -> None:
    rows = db.execute(
        select(Asset, Department)
        .outerjoin(Department, Department.id == Asset.department_id)
        .where(_active(org_id))
        .order_by(Asset.type, Asset.name)
    ).all()
    table = Table(
        ["Name", "Type", "Identifier", "Department", "Owner", "Criticality", "Monitoring", "Risk"],
        [
            [
                a.name,
                TYPE_LABEL.get(a.type, a.type),
                a.identifier,
                d.name if d else "—",
                _name(db, a.owner_user_id) if a.owner_user_id else "—",
                a.criticality.capitalize(),
                a.monitoring_status.replace("_", " ").capitalize(),
                a.risk_level.capitalize(),
            ]
            for a, d in rows
        ],
        [0.16, 0.1, 0.2, 0.1, 0.12, 0.09, 0.13, 0.1],
    )
    c.kpis = [
        ("Assets", str(len(rows)), "Active, registered"),
        ("Critical assets", str(sum(1 for a, _ in rows if a.criticality == "critical")), ""),
        (
            "Awaiting authorisation",
            str(sum(1 for a, _ in rows if a.monitoring_status == "not_monitored")),
            "",
        ),
    ]
    c.sections.append(Section("All assets", table=table))
    c.csv = table


def _endpoint_health(db, org_id, start, end, c: ReportContent) -> None:
    agents = db.execute(
        select(Agent, Asset)
        .join(Asset, Asset.id == Agent.asset_id)
        .where(
            Agent.organisation_id == org_id,
            Agent.status == "active",
            Agent.source.in_(("smecm_agent", "wazuh")),
            _active(org_id),
        )
        .order_by(Agent.hostname)
    ).all()

    def flag(v):
        return "Yes" if v is True else "No" if v is False else "Unknown"

    table = Table(
        [
            "Device",
            "OS",
            "Agent",
            "Status",
            "Last seen",
            "Antivirus",
            "Firewall",
            "Encrypted",
            "Security updates",
        ],
        [
            [
                a.hostname,
                " ".join(p for p in (a.os_name, a.os_version) if p) or "—",
                "Wazuh" if a.source == "wazuh" else f"SMECM {a.agent_version or ''}",
                "Online" if is_online(a) or a.source == "wazuh" else "Offline",
                _d(a.last_seen_at),
                flag((a.inventory or {}).get("antivirus_enabled")),
                flag((a.inventory or {}).get("firewall_enabled")),
                flag((a.inventory or {}).get("disk_encrypted")),
                str((a.inventory or {}).get("pending_security_updates", "—")),
            ]
            for a, _ in agents
        ],
        [0.15, 0.17, 0.1, 0.08, 0.1, 0.09, 0.09, 0.1, 0.12],
    )
    online = sum(1 for a, _ in agents if is_online(a))
    c.kpis = [
        ("Devices with agents", str(len(agents)), ""),
        ("Online", str(online), "Reported in the last 15 minutes"),
        (
            "Health findings",
            str(
                db.scalar(
                    select(func.count()).where(
                        Finding.organisation_id == org_id,
                        Finding.status == "open",
                        Finding.check_type == "endpoint_health",
                    )
                )
                or 0
            ),
            "Open now",
        ),
    ]
    c.sections.append(
        Section("Devices", table=table)
        if agents
        else Section("Devices", paragraphs=["No devices have a monitoring agent installed yet."])
    )
    c.csv = table


def _findings(db, org_id, start, end, c: ReportContent) -> None:
    rows = _open_findings(db, org_id)
    table = Table(
        ["Severity", "Issue", "Asset", "Open since", "What to do"],
        [
            [f.severity.capitalize(), f.title, a.name, _d(f.first_seen_at), f.recommendation]
            for f, a in rows
        ],
        [0.1, 0.22, 0.15, 0.1, 0.43],
    )
    by_sev = {s: sum(1 for f, _ in rows if f.severity == s) for s in SEV_ORDER}
    c.kpis = [(s.capitalize(), str(by_sev[s]), "") for s in ("critical", "high", "medium", "low")]
    resolved = (
        db.scalar(
            select(func.count()).where(
                Finding.organisation_id == org_id,
                Finding.resolved_at >= start,
                Finding.resolved_at < end,
            )
        )
        or 0
    )
    c.sections.append(
        Section(
            "Overview",
            paragraphs=[
                f"{len(rows)} open finding(s) on monitored assets. "
                f"{resolved} finding(s) were resolved during this period."
            ],
        )
    )
    c.sections.append(
        Section("Open findings", table=table)
        if rows
        else Section("Open findings", paragraphs=["No open findings."])
    )
    c.csv = table


def _incidents(db, org_id, start, end, c: ReportContent) -> None:
    rows = list(
        db.scalars(
            select(Incident)
            .where(
                Incident.organisation_id == org_id,
                Incident.created_at >= start,
                Incident.created_at < end,
            )
            .order_by(Incident.created_at)
        )
    )

    def ttc(i: Incident) -> str:
        if not i.closed_at:
            return "Open"
        hours = (i.closed_at - i.created_at).total_seconds() / 3600
        return f"{hours:.1f} h" if hours < 48 else f"{hours / 24:.1f} days"

    table = Table(
        [
            "Reference",
            "Title",
            "Severity",
            "Category",
            "Status",
            "Opened",
            "Time to close",
            "Closure",
        ],
        [
            [
                i.reference,
                i.title,
                i.severity.capitalize(),
                i.category.replace("_", " ").capitalize(),
                i.status.capitalize(),
                _d(i.created_at),
                ttc(i),
                (i.closure_reason or "—").replace("_", " "),
            ]
            for i in rows
        ],
        [0.09, 0.27, 0.08, 0.13, 0.1, 0.1, 0.1, 0.13],
    )
    c.kpis = [
        ("Incidents opened", str(len(rows)), "During this period"),
        ("Still open", str(sum(1 for i in rows if i.status not in ("resolved", "closed"))), ""),
        ("Critical", str(sum(1 for i in rows if i.severity == "critical")), ""),
    ]
    c.sections.append(
        Section("Incidents", table=table)
        if rows
        else Section("Incidents", paragraphs=["No incidents were opened during this period."])
    )
    c.csv = table


def _remediation(db, org_id, start, end, c: ReportContent) -> None:
    rows = list(
        db.scalars(
            select(RemediationTask)
            .where(
                RemediationTask.organisation_id == org_id,
                (RemediationTask.created_at < end)
                & (
                    (RemediationTask.completed_at.is_(None))
                    | (RemediationTask.completed_at >= start)
                ),
            )
            .order_by(RemediationTask.due_at.nulls_last())
        )
    )
    done = [
        t
        for t in rows
        if t.status == "verified" and t.completed_at and start <= t.completed_at < end
    ]
    on_time = [t for t in done if t.due_at and t.completed_at <= t.due_at]
    overdue = [
        t for t in rows if t.status in ("open", "in_progress") and t.due_at and t.due_at < end
    ]
    table = Table(
        ["Task", "Priority", "Assignee", "Status", "Due", "Completed", "On time"],
        [
            [
                t.title,
                t.priority.capitalize(),
                _name(db, t.assignee_id),
                t.status.replace("_", " ").capitalize(),
                _d(t.due_at),
                _d(t.completed_at),
                "—"
                if not t.completed_at or not t.due_at
                else ("Yes" if t.completed_at <= t.due_at else "No"),
            ]
            for t in rows
        ],
        [0.32, 0.09, 0.15, 0.12, 0.11, 0.11, 0.1],
    )
    c.kpis = [
        ("Fixes verified", str(len(done)), "During this period"),
        ("On time", f"{round(100 * len(on_time) / len(done))}%" if done else "—", ""),
        ("Overdue", str(len(overdue)), "Open past their due date"),
    ]
    c.sections.append(
        Section("Tasks", table=table)
        if rows
        else Section("Tasks", paragraphs=["No remediation tasks during this period."])
    )
    c.csv = table


def _coverage(db, org_id, start, end, c: ReportContent) -> None:
    posture = compute_posture(db, org_id)
    assets = list(db.scalars(select(Asset).where(_active(org_id)).order_by(Asset.name)))
    fresh = {
        r
        for r in db.scalars(
            select(MonitoringCheck.asset_id).where(
                MonitoringCheck.organisation_id == org_id,
                MonitoringCheck.enabled.is_(True),
                MonitoringCheck.last_status.in_(("ok", "warning", "failing")),
            )
        )
    }
    groups: dict[str, list[Asset]] = {}
    for a in assets:
        groups.setdefault(TYPE_LABEL.get(a.type, a.type), []).append(a)
    c.kpis = [
        ("Coverage", f"{posture['confidence']}%", "Assets with current monitoring data"),
        ("Monitored", str(posture["monitored_assets"]), ""),
        ("Checks failing to run", str(posture["assets_with_check_errors"]), "Assets"),
    ]
    c.sections.append(
        Section(
            "By asset type",
            table=Table(
                ["Type", "Assets", "Monitored", "Not monitored"],
                [
                    [
                        t,
                        str(len(a)),
                        str(sum(1 for x in a if x.id in fresh)),
                        str(sum(1 for x in a if x.id not in fresh)),
                    ]
                    for t, a in sorted(groups.items())
                ],
                [0.4, 0.2, 0.2, 0.2],
            ),
        )
    )
    missing = [a for a in assets if a.id not in fresh]
    if missing:
        c.sections.append(
            Section(
                "Assets without monitoring",
                table=Table(
                    ["Asset", "Type", "Why"],
                    [
                        [
                            a.name,
                            TYPE_LABEL.get(a.type, a.type),
                            "Awaiting authorisation"
                            if a.monitoring_status == "not_monitored"
                            else "No agent or collector reporting"
                            if a.type not in ("website", "domain")
                            else "Checks not running",
                        ]
                        for a in missing
                    ],
                    [0.4, 0.2, 0.4],
                ),
            )
        )


BUILDERS = {
    "executive": _executive,
    "asset_inventory": _asset_inventory,
    "endpoint_health": _endpoint_health,
    "findings": _findings,
    "incidents": _incidents,
    "remediation": _remediation,
    "coverage": _coverage,
}
