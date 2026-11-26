"""Agent lifecycle and telemetry processing.

The organisation and asset for every piece of telemetry come from the authenticated agent
record, never from the payload.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.endpoints.detection import DEFAULT_SEVERITY, DEFAULT_SUMMARY, detect
from app.endpoints.health import evaluate_inventory
from app.models import Agent, Asset, AssetAuthorisation, CheckRun, MonitoringCheck, SecurityEvent
from app.monitoring.checks import Issue, Outcome
from app.monitoring.engine import EmailJob, apply_issues, refresh_asset
from app.monitoring.scoring import record_snapshot

HEARTBEAT_SECONDS = 300
OFFLINE_AFTER = timedelta(minutes=15)
EVENT_RETENTION_DAYS = 30


def is_online(agent: Agent, now: datetime | None = None) -> bool:
    if agent.status != "active" or agent.last_seen_at is None:
        return False
    return (now or datetime.now(UTC)) - agent.last_seen_at < OFFLINE_AFTER


def ensure_agent_checks(
    db: Session, asset: Asset, kinds: tuple[str, ...] = ("agent_heartbeat", "endpoint_health")
) -> dict[str, MonitoringCheck]:
    existing = {
        c.check_type: c
        for c in db.scalars(select(MonitoringCheck).where(MonitoringCheck.asset_id == asset.id))
    }
    for check_type in kinds:
        if check_type not in existing:
            check = MonitoringCheck(
                organisation_id=asset.organisation_id,
                asset_id=asset.id,
                check_type=check_type,
                interval_minutes=HEARTBEAT_SECONDS // 60,
                enabled=True,
            )
            db.add(check)
            existing[check_type] = check
    db.flush()
    return existing


def authorise_by_agent(db: Session, asset: Asset, agent: Agent, evidence: dict) -> None:
    """An installed agent is technical proof the organisation controls the device."""
    db.add(
        AssetAuthorisation(
            organisation_id=asset.organisation_id,
            asset_id=asset.id,
            method="agent",
            challenge=f"agent:{agent.id}",
            status="verified",
            evidence=evidence,
            verified_at=datetime.now(UTC),
        )
    )
    if asset.monitoring_status == "not_monitored":
        asset.monitoring_status = "authorised"


def record_check(db: Session, check: MonitoringCheck, outcome: Outcome, now: datetime) -> None:
    """Update a check; keep a run in the history only when its result changes."""
    changed = (check.last_status, check.last_summary) != (outcome.status, outcome.summary[:400])
    check.last_run_at = now
    check.last_status = outcome.status
    check.last_summary = outcome.summary[:400]
    if changed:
        db.add(
            CheckRun(
                organisation_id=check.organisation_id,
                asset_id=check.asset_id,
                check_id=check.id,
                check_type=check.check_type,
                started_at=now,
                completed_at=now,
                duration_ms=0,
                status=outcome.status,
                summary=outcome.summary[:400],
                result=outcome.data,
            )
        )


def process_heartbeat(
    db: Session,
    agent: Agent,
    inventory: dict[str, Any],
    agent_version: str,
    ip: str | None,
    now: datetime | None = None,
) -> list[EmailJob]:
    now = now or datetime.now(UTC)
    asset = db.get(Asset, agent.asset_id)
    agent.last_seen_at = now
    agent.last_ip = ip
    agent.agent_version = agent_version
    agent.inventory = inventory
    agent.hostname = inventory.get("hostname") or agent.hostname
    agent.os_family = inventory.get("os_family")
    agent.os_name = inventory.get("os_name")
    agent.os_version = inventory.get("os_version")
    asset.last_seen_at = now
    asset.last_successful_check_at = now
    if not asset.technology and agent.os_name:
        asset.technology = " ".join(p for p in (agent.os_name, agent.os_version) if p)[:200]

    checks = ensure_agent_checks(db, asset)
    emails: list[EmailJob] = []
    online = Outcome("ok", f"Online · agent {agent_version}", reachable=True)
    record_check(db, checks["agent_heartbeat"], online, now)
    emails += apply_issues(db, asset, "agent_heartbeat", [], evaluated=True, now=now)

    health = evaluate_inventory(inventory, asset.type)
    record_check(db, checks["endpoint_health"], health, now)
    emails += apply_issues(db, asset, "endpoint_health", health.issues, evaluated=True, now=now)

    db.flush()
    refresh_asset(db, asset)
    record_snapshot(db, asset.organisation_id)
    return emails


def normalise_event(raw: dict[str, Any]) -> dict[str, Any]:
    event_type = raw["event_type"]
    occurred = raw["timestamp"]
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=UTC)
    return {
        "source_event_id": raw["event_id"],
        "event_type": event_type,
        "severity": raw.get("severity") or DEFAULT_SEVERITY[event_type],
        "summary": (raw.get("summary") or DEFAULT_SUMMARY[event_type])[:300],
        "occurred_at": occurred,
        "data": raw.get("data") or {},
    }


def ingest_events(
    db: Session, agent: Agent, events: list[dict[str, Any]], now: datetime | None = None
) -> tuple[int, int, list[EmailJob]]:
    """Store events (idempotent on the agent's event id) and run detections."""
    now = now or datetime.now(UTC)
    # Reject timestamps far in the future; clamp to "now" so detections stay meaningful.
    rows = []
    for e in events:
        n = normalise_event(e)
        if n["occurred_at"] > now + timedelta(minutes=5):
            n["occurred_at"] = now
        rows.append(
            {
                "id": uuid.uuid4(),
                "organisation_id": agent.organisation_id,
                "asset_id": agent.asset_id,
                "agent_id": agent.id,
                "received_at": now,
                **n,
            }
        )
    inserted_ids = list(
        db.scalars(
            insert(SecurityEvent)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["agent_id", "source_event_id"])
            .returning(SecurityEvent.id)
        )
    )
    if agent.source == "wazuh":
        agent.last_seen_at = now  # for Wazuh agents, an alert is our only sign of life
    if not inserted_ids:
        return 0, len(rows), []

    new_events = list(db.scalars(select(SecurityEvent).where(SecurityEvent.id.in_(inserted_ids))))
    asset = db.get(Asset, agent.asset_id)
    issues = detect(db, asset.id, new_events)
    emails: list[EmailJob] = []
    if issues:
        emails = apply_issues(db, asset, "detection", issues, evaluated=False, now=now)
        db.flush()
        refresh_asset(db, asset)
        record_snapshot(db, asset.organisation_id)
    return len(inserted_ids), len(rows) - len(inserted_ids), emails


def sweep_offline(db: Session, now: datetime | None = None) -> list[EmailJob]:
    """Raise 'device stopped reporting' for our agents that missed their heartbeats.

    Wazuh agents are skipped: they only send us alerts, so silence is normal for them.
    """
    now = now or datetime.now(UTC)
    emails: list[EmailJob] = []
    rows = db.execute(
        select(Agent, MonitoringCheck)
        .join(
            MonitoringCheck,
            (MonitoringCheck.asset_id == Agent.asset_id)
            & (MonitoringCheck.check_type == "agent_heartbeat"),
        )
        .join(Asset, Asset.id == Agent.asset_id)
        .where(
            Agent.status == "active",
            Agent.source.in_(("smecm_agent", "collector")),
            Agent.last_seen_at < now - OFFLINE_AFTER,
            MonitoringCheck.last_status != "error",
            Asset.status == "active",
        )
    ).all()
    for agent, check in rows:
        asset = db.get(Asset, agent.asset_id)
        outcome = Outcome("error", f"No heartbeat since {agent.last_seen_at:%d %b %H:%M} UTC")
        record_check(db, check, outcome, now)
        emails += apply_issues(
            db,
            asset,
            "agent_heartbeat",
            [Issue("agent_offline", {"last_seen_at": agent.last_seen_at.isoformat()})],
            evaluated=True,
            now=now,
        )
        db.flush()
        refresh_asset(db, asset)
        record_snapshot(db, asset.organisation_id)
    return emails
