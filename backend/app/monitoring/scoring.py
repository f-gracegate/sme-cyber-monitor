"""Organisation security posture.

Finding severity (per issue) and posture (per organisation) are separate measurements.

* The score only exists once at least one asset has real monitoring data.
* Findings are cleared only by a check that actually ran, so turning monitoring off, or a check
  failing to run, never improves the score. Those gaps are reported as coverage instead.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Agent, Asset, Finding, MonitoringCheck, RiskScoreSnapshot

PENALTY = {"critical": 30, "high": 15, "medium": 6, "low": 2, "informational": 0}
MONITORABLE_TYPES = ("website", "domain")


def compute_posture(db: Session, org_id: uuid.UUID) -> dict[str, Any]:
    active_asset = (Asset.organisation_id == org_id) & (Asset.status == "active")
    counts = dict(
        db.execute(
            select(Finding.severity, func.count())
            .join(Asset, Asset.id == Finding.asset_id)
            .where(Finding.organisation_id == org_id, Finding.status == "open", active_asset)
            .group_by(Finding.severity)
        ).all()
    )
    monitored = (
        db.scalar(
            select(func.count(distinct(MonitoringCheck.asset_id)))
            .join(Asset, Asset.id == MonitoringCheck.asset_id)
            .where(
                MonitoringCheck.organisation_id == org_id,
                MonitoringCheck.last_run_at.is_not(None),
                MonitoringCheck.last_status.in_(("ok", "warning", "failing")),
                active_asset,
            )
        )
        or 0
    )
    with_errors = (
        db.scalar(
            select(func.count(distinct(MonitoringCheck.asset_id)))
            .join(Asset, Asset.id == MonitoringCheck.asset_id)
            .where(
                MonitoringCheck.organisation_id == org_id,
                MonitoringCheck.enabled.is_(True),
                MonitoringCheck.last_status == "error",
                active_asset,
            )
        )
        or 0
    )
    disabled = (
        db.scalar(
            select(func.count())
            .select_from(MonitoringCheck)
            .join(Asset, Asset.id == MonitoringCheck.asset_id)
            .where(
                MonitoringCheck.organisation_id == org_id,
                MonitoringCheck.enabled.is_(False),
                active_asset,
            )
        )
        or 0
    )
    monitorable = (
        db.scalar(select(func.count()).where(active_asset, Asset.type.in_(MONITORABLE_TYPES))) or 0
    )
    # Devices become monitorable once an agent is installed on them.
    monitorable += (
        db.scalar(
            select(func.count(distinct(Agent.asset_id)))
            .join(Asset, Asset.id == Agent.asset_id)
            .where(
                Agent.organisation_id == org_id,
                Agent.status == "active",
                active_asset,
                Asset.type.not_in(MONITORABLE_TYPES),
            )
        )
        or 0
    )

    penalty = sum(PENALTY.get(sev, 0) * n for sev, n in counts.items())
    score = max(0, 100 - penalty) if monitored else None
    return {
        "score": score,
        "open_by_severity": {s: counts.get(s, 0) for s in PENALTY},
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
        "updated_at": datetime.now(UTC),
    }
    stmt = insert(RiskScoreSnapshot).values(
        id=uuid.uuid4(), organisation_id=org_id, day=datetime.now(UTC).date(), **values
    )
    db.execute(stmt.on_conflict_do_update(index_elements=["organisation_id", "day"], set_=values))
    return posture
