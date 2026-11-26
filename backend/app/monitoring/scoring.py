"""Organisation security posture (model v2).

Finding severity (per issue) and posture (per organisation) are separate measurements.

The posture score is a weighted blend of five components, each 0-100:

==================  ======  =====================================================================
Component           Weight  What it measures
==================  ======  =====================================================================
findings            35%     Open findings, weighted by severity
coverage            25%     Share of the estate with current monitoring data
endpoint_health     15%     Agents reporting, and devices free of health findings
remediation         15%     Overdue fixes and urgent findings nobody has picked up
incidents           10%     Open incidents, weighted by severity
==================  ======  =====================================================================

Rules that keep the score honest:

* No score until at least one asset has real monitoring data.
* Unmonitored assets count against coverage, so switching monitoring off, or a check failing,
  lowers the score instead of hiding problems. Findings only clear after a check really ran.
* A component with nothing to measure (for example no agents installed) is left out and its
  weight shared by the others; it never counts as a perfect 100.
* ``confidence`` is the share of the estate the score is based on, shown next to the score.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    Asset,
    Finding,
    Incident,
    MonitoringCheck,
    RemediationTask,
    RiskScoreSnapshot,
)

WEIGHTS = {
    "findings": 0.35,
    "coverage": 0.25,
    "endpoint_health": 0.15,
    "remediation": 0.15,
    "incidents": 0.10,
}
FINDING_PENALTY = {"critical": 25, "high": 12, "medium": 5, "low": 1, "informational": 0}
INCIDENT_PENALTY = {"critical": 40, "high": 20, "medium": 10, "low": 5}
# Cloud accounts can't be monitored yet; counting them would penalise customers for our gap.
UNMONITORABLE_TYPES = ("cloud_account", "cloud_service")
FRESH_FOR = timedelta(hours=26)
OPEN_INCIDENT = ("open", "investigating", "contained")
OPEN_TASK = ("open", "in_progress")


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def compute_posture(db: Session, org_id: uuid.UUID) -> dict[str, Any]:
    now = datetime.now(UTC)
    active_asset = (Asset.organisation_id == org_id) & (Asset.status == "active")

    counts = dict(
        db.execute(
            select(Finding.severity, func.count())
            .join(Asset, Asset.id == Finding.asset_id)
            .where(Finding.organisation_id == org_id, Finding.status == "open", active_asset)
            .group_by(Finding.severity)
        ).all()
    )
    open_by_severity = {s: counts.get(s, 0) for s in FINDING_PENALTY}

    monitorable = _count(
        db, select(func.count()).where(active_asset, Asset.type.not_in(UNMONITORABLE_TYPES))
    )
    monitored = _count(
        db,
        select(func.count(distinct(MonitoringCheck.asset_id)))
        .join(Asset, Asset.id == MonitoringCheck.asset_id)
        .where(
            MonitoringCheck.organisation_id == org_id,
            MonitoringCheck.enabled.is_(True),
            MonitoringCheck.last_status.in_(("ok", "warning", "failing")),
            MonitoringCheck.last_run_at >= now - FRESH_FOR,
            active_asset,
        ),
    )
    with_errors = _count(
        db,
        select(func.count(distinct(MonitoringCheck.asset_id)))
        .join(Asset, Asset.id == MonitoringCheck.asset_id)
        .where(
            MonitoringCheck.organisation_id == org_id,
            MonitoringCheck.enabled.is_(True),
            MonitoringCheck.last_status == "error",
            active_asset,
        ),
    )
    disabled = _count(
        db,
        select(func.count())
        .select_from(MonitoringCheck)
        .join(Asset, Asset.id == MonitoringCheck.asset_id)
        .where(
            MonitoringCheck.organisation_id == org_id,
            MonitoringCheck.enabled.is_(False),
            active_asset,
        ),
    )

    components: dict[str, int | None] = {}
    components["findings"] = max(
        0, 100 - sum(FINDING_PENALTY[s] * n for s, n in open_by_severity.items())
    )
    components["coverage"] = round(100 * monitored / monitorable) if monitorable else None

    agents = list(
        db.scalars(
            select(Agent)
            .join(Asset, Asset.id == Agent.asset_id)
            .where(
                Agent.organisation_id == org_id,
                Agent.status == "active",
                Agent.source == "smecm_agent",
                active_asset,
            )
        )
    )
    if agents:
        online = sum(
            1 for a in agents if a.last_seen_at and now - a.last_seen_at < timedelta(minutes=15)
        )
        unhealthy = _count(
            db,
            select(func.count(distinct(Finding.asset_id))).where(
                Finding.asset_id.in_([a.asset_id for a in agents]),
                Finding.status == "open",
                Finding.check_type == "endpoint_health",
            ),
        )
        components["endpoint_health"] = round(
            50 * online / len(agents) + 50 * (len(agents) - unhealthy) / len(agents)
        )
    else:
        components["endpoint_health"] = None

    overdue = _count(
        db,
        select(func.count()).where(
            RemediationTask.organisation_id == org_id,
            RemediationTask.status.in_(OPEN_TASK),
            RemediationTask.due_at < now,
        ),
    )
    has_task = (
        select(RemediationTask.id)
        .where(
            RemediationTask.finding_id == Finding.id,
            RemediationTask.status.in_((*OPEN_TASK, "done")),
        )
        .exists()
    )
    neglected = _count(
        db,
        select(func.count())
        .select_from(Finding)
        .join(Asset, Asset.id == Finding.asset_id)
        .where(
            Finding.organisation_id == org_id,
            Finding.status == "open",
            Finding.severity.in_(("critical", "high")),
            Finding.first_seen_at < now - timedelta(days=3),
            ~has_task,
            active_asset,
        ),
    )
    components["remediation"] = max(0, 100 - 10 * overdue - 5 * neglected)

    incident_rows = dict(
        db.execute(
            select(Incident.severity, func.count())
            .where(Incident.organisation_id == org_id, Incident.status.in_(OPEN_INCIDENT))
            .group_by(Incident.severity)
        ).all()
    )
    components["incidents"] = max(
        0, 100 - sum(INCIDENT_PENALTY.get(s, 10) * n for s, n in incident_rows.items())
    )

    if monitored:
        used = {k: v for k, v in components.items() if v is not None}
        weight = sum(WEIGHTS[k] for k in used)
        score = round(sum(WEIGHTS[k] * v for k, v in used.items()) / weight)
    else:
        score = None

    return {
        "score": score,
        "components": components,
        "confidence": round(100 * monitored / monitorable) if monitorable else 0,
        "open_by_severity": open_by_severity,
        "open_incidents": sum(incident_rows.values()),
        "overdue_tasks": overdue,
        "neglected_findings": neglected,
        "monitored_assets": monitored,
        "monitorable_assets": monitorable,
        "assets_with_check_errors": with_errors,
        "disabled_checks": disabled,
    }


def record_snapshot(db: Session, org_id: uuid.UUID) -> dict[str, Any]:
    posture = compute_posture(db, org_id)
    if posture["score"] is None:
        return posture
    sev = posture["open_by_severity"]
    values = {
        "score": posture["score"],
        "open_critical": sev["critical"],
        "open_high": sev["high"],
        "open_medium": sev["medium"],
        "open_low": sev["low"],
        "monitored_assets": posture["monitored_assets"],
        "components": posture["components"],
        "confidence": posture["confidence"],
        "updated_at": datetime.now(UTC),
    }
    stmt = insert(RiskScoreSnapshot).values(
        id=uuid.uuid4(), organisation_id=org_id, day=datetime.now(UTC).date(), **values
    )
    db.execute(stmt.on_conflict_do_update(index_elements=["organisation_id", "day"], set_=values))
    return posture
