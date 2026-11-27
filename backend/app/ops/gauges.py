"""Health gauges for /api/metrics: is the platform keeping up?"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.observability import worker_status
from app.models import Incident, MonitoringCheck, Notification, Organisation


def collect_gauges() -> dict[str, float]:
    workers, age = worker_status()
    now = datetime.now(UTC)
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        overdue = db.scalar(
            select(func.count()).where(
                MonitoringCheck.enabled.is_(True),
                MonitoringCheck.next_run_at < now - timedelta(minutes=5),
            )
        )
        push_backlog = db.scalar(
            select(func.count()).where(
                Notification.pushed_at.is_(None),
                Notification.created_at > now - timedelta(minutes=30),
            )
        )
        open_incidents = db.scalar(
            select(func.count()).where(Incident.status.in_(("open", "investigating", "contained")))
        )
        orgs = db.scalar(
            select(func.count()).where(
                Organisation.status == "active", Organisation.deleted_at.is_(None)
            )
        )
    finally:
        db.close()
    return {
        "workers_alive": workers,
        "worker_heartbeat_age_seconds": round(age, 1) if age is not None else -1,
        "checks_overdue": overdue or 0,
        "push_backlog": push_backlog or 0,
        "incidents_open": open_incidents or 0,
        "organisations_active": orgs or 0,
    }
