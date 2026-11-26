"""Network collector processing: health, device availability and network event detections.

A collector is stored as an ``Agent`` with ``source="collector"`` attached to its own asset (an
on-premises network device the organisation controls). Everything it reports is attributed to
the collector's organisation; device hints in events are matched only against that
organisation's own assets.
"""

import ipaddress
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.endpoints.service import ensure_agent_checks, record_check
from app.models import Agent, Asset, MonitoringCheck, SecurityEvent
from app.monitoring.checks import Issue, Outcome
from app.monitoring.engine import RUNNABLE_ASSET_STATES, EmailJob, apply_issues, refresh_asset
from app.monitoring.scoring import record_snapshot

NETWORK_TYPES = ("firewall", "router", "switch", "network_device")
HEARTBEAT_SECONDS = 60
PROBE_SECONDS = 60
UNREACHABLE_AFTER = 3
QUEUE_WARNING = 10_000
WINDOW = timedelta(minutes=10)
ADMIN_FAILURE_THRESHOLD = 5
DENY_SCAN_THRESHOLD = 500

DEFAULT_SEVERITY = {
    "network.firewall_deny": "informational",
    "network.config_change": "high",
    "network.admin_login_failure": "low",
    "network.admin_login_success": "informational",
    "network.vpn_login": "informational",
    "network.ids_alert": "medium",
    "network.zeek_notice": "low",
}
DEFAULT_SUMMARY = {
    "network.firewall_deny": "Connections blocked by firewall",
    "network.config_change": "Configuration changed",
    "network.admin_login_failure": "Failed admin login",
    "network.admin_login_success": "Admin login",
    "network.vpn_login": "VPN login",
    "network.ids_alert": "Intrusion detection alert",
    "network.zeek_notice": "Network notice",
}
_SUSPICIOUS_NOTICES = {
    "SSH::Password_Guessing",
    "SSL::Invalid_Server_Cert",
    "Software::Vulnerable_Version",
    "HTTP::SQL_Injection_Attacker",
}


def collector_asset_ids(db: Session, org_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Agent.asset_id).where(
                Agent.organisation_id == org_id, Agent.source == "collector"
            )
        )
    )


def probe_targets(db: Session, collector: Agent) -> list[dict]:
    """Authorised network devices of the collector's organisation. Nothing else is ever probed."""
    exclude = collector_asset_ids(db, collector.organisation_id)
    rows = db.scalars(
        select(Asset)
        .where(
            Asset.organisation_id == collector.organisation_id,
            Asset.status == "active",
            Asset.type.in_(NETWORK_TYPES),
            Asset.monitoring_status.in_(RUNNABLE_ASSET_STATES),
        )
        .order_by(Asset.name)
        .limit(500)
    )
    return [
        {"asset_id": a.id, "name": a.name, "address": a.identifier, "type": a.type}
        for a in rows
        if a.id not in exclude
    ]


def _availability_check(db: Session, asset: Asset) -> MonitoringCheck:
    check = db.scalar(
        select(MonitoringCheck).where(
            MonitoringCheck.asset_id == asset.id,
            MonitoringCheck.check_type == "device_availability",
        )
    )
    if check is None:
        check = MonitoringCheck(
            organisation_id=asset.organisation_id,
            asset_id=asset.id,
            check_type="device_availability",
            interval_minutes=PROBE_SECONDS // 60,
            enabled=True,
        )
        db.add(check)
        db.flush()
    return check


def process_heartbeat(
    db: Session,
    collector: Agent,
    version: str,
    health: dict[str, Any],
    probes: list[dict],
    traffic: dict | None,
    ip: str | None,
    now: datetime | None = None,
) -> list[EmailJob]:
    now = now or datetime.now(UTC)
    asset = db.get(Asset, collector.asset_id)
    collector.last_seen_at = now
    collector.last_ip = ip
    collector.agent_version = version
    collector.hostname = health.get("hostname") or collector.hostname
    collector.inventory = {**health, "traffic": traffic}
    asset.last_seen_at = asset.last_successful_check_at = now

    checks = ensure_agent_checks(db, asset, kinds=("agent_heartbeat", "collector_health"))
    emails: list[EmailJob] = []
    record_check(db, checks["agent_heartbeat"], Outcome("ok", f"Online · collector {version}"), now)
    emails += apply_issues(db, asset, "agent_heartbeat", [], evaluated=True, now=now)

    issues = []
    if health.get("events_dropped", 0) > 0 or health.get("queue_depth", 0) > QUEUE_WARNING:
        issues.append(
            Issue(
                "collector_dropping_events",
                {
                    "events_dropped": health.get("events_dropped"),
                    "queue_depth": health.get("queue_depth"),
                },
            )
        )
    summary = (
        f"Forwarding · {health.get('events_forwarded', 0)} events since last heartbeat, "
        f"queue {health.get('queue_depth', 0)}"
    )
    record_check(
        db,
        checks["collector_health"],
        Outcome("warning" if issues else "ok", summary, issues=issues),
        now,
    )
    emails += apply_issues(db, asset, "collector_health", issues, evaluated=True, now=now)
    db.flush()
    refresh_asset(db, asset)

    allowed = {t["asset_id"] for t in probe_targets(db, collector)}
    for probe in probes:
        if probe["asset_id"] not in allowed:
            continue  # only authorised devices of this organisation
        emails += _apply_probe(db, collector, probe, now)

    record_snapshot(db, collector.organisation_id)
    return emails


def _apply_probe(db: Session, collector: Agent, probe: dict, now: datetime) -> list[EmailJob]:
    device = db.get(Asset, probe["asset_id"])
    check = _availability_check(db, device)
    reachable = bool(probe["reachable"])
    check.consecutive_failures = 0 if reachable else check.consecutive_failures + 1
    check.state = {
        **(check.state or {}),
        "latency_ms": probe.get("latency_ms"),
        "method": probe.get("method"),
        "collector_id": str(collector.id),
    }
    if reachable:
        latency = probe.get("latency_ms")
        outcome = Outcome(
            "ok",
            f"Reachable{f' · {latency:.0f} ms' if latency is not None else ''}",
            reachable=True,
        )
        device.last_seen_at = device.last_successful_check_at = now
    else:
        issues = (
            [
                Issue(
                    "network_device_unreachable",
                    {
                        "address": device.identifier,
                        "failed_checks": check.consecutive_failures,
                        "collector": collector.hostname,
                    },
                )
            ]
            if check.consecutive_failures >= UNREACHABLE_AFTER
            else []
        )
        outcome = Outcome(
            "failing", f"Not responding ({check.consecutive_failures} check(s))", issues=issues
        )
    record_check(db, check, outcome, now)
    emails = apply_issues(
        db, device, "device_availability", outcome.issues, evaluated=True, now=now
    )
    db.flush()
    refresh_asset(db, device)
    return emails


def _match_device(
    db: Session, org_id: uuid.UUID, hint: str | None, cache: dict
) -> uuid.UUID | None:
    if not hint:
        return None
    key = hint.strip().lower()
    if key not in cache:
        cache[key] = db.scalar(
            select(Asset.id)
            .where(
                Asset.organisation_id == org_id,
                Asset.status == "active",
                (func.lower(Asset.identifier) == key) | (func.lower(Asset.name) == key),
            )
            .limit(1)
        )
    return cache[key]


def ingest_network_events(
    db: Session, collector: Agent, events: list[dict], now: datetime | None = None
) -> tuple[int, int, list[EmailJob]]:
    now = now or datetime.now(UTC)
    cache: dict = {}
    rows = []
    for e in events:
        occurred = e["timestamp"] if e["timestamp"].tzinfo else e["timestamp"].replace(tzinfo=UTC)
        if occurred > now + timedelta(minutes=5):
            occurred = now
        asset_id = (
            _match_device(db, collector.organisation_id, e.get("device"), cache)
            or collector.asset_id
        )
        rows.append(
            {
                "id": uuid.uuid4(),
                "organisation_id": collector.organisation_id,
                "asset_id": asset_id,
                "agent_id": collector.id,
                "received_at": now,
                "source_event_id": e["event_id"],
                "event_type": e["event_type"],
                "severity": e.get("severity") or DEFAULT_SEVERITY[e["event_type"]],
                "summary": (e.get("summary") or DEFAULT_SUMMARY[e["event_type"]])[:300],
                "occurred_at": occurred,
                "data": {**(e.get("data") or {}), "device": e.get("device"), "count": e["count"]},
            }
        )
    inserted = list(
        db.scalars(
            insert(SecurityEvent)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["agent_id", "source_event_id"])
            .returning(SecurityEvent.id)
        )
    )
    if not inserted:
        return 0, len(rows), []

    new_events = list(db.scalars(select(SecurityEvent).where(SecurityEvent.id.in_(inserted))))
    by_asset: dict[uuid.UUID, list[SecurityEvent]] = defaultdict(list)
    for event in new_events:
        by_asset[event.asset_id].append(event)
    emails: list[EmailJob] = []
    for asset_id, asset_events in by_asset.items():
        issues = detect(db, asset_id, asset_events)
        if issues:
            asset = db.get(Asset, asset_id)
            emails += apply_issues(db, asset, "detection", issues, evaluated=False, now=now)
            db.flush()
            refresh_asset(db, asset)
    if emails or any(by_asset):
        record_snapshot(db, collector.organisation_id)
    return len(inserted), len(rows) - len(inserted), emails


def _evidence(event: SecurityEvent) -> dict:
    keep = {
        "device",
        "src_ip",
        "dst_ip",
        "dst_port",
        "signature",
        "category",
        "note",
        "user",
        "suricata_severity",
        "message",
        "count",
        "proto",
    }
    return {
        "summary": event.summary,
        "occurred_at": event.occurred_at.isoformat(),
        **{k: v for k, v in (event.data or {}).items() if k in keep and v is not None},
    }


def _count_in_window(
    db: Session, asset_id, event_type: str, until: datetime, src_ip: str | None = None
) -> int:
    stmt = select(
        func.coalesce(func.sum(SecurityEvent.data["count"].astext.cast(Integer)), 0)
    ).where(
        SecurityEvent.asset_id == asset_id,
        SecurityEvent.event_type == event_type,
        SecurityEvent.occurred_at >= until - WINDOW,
        SecurityEvent.occurred_at <= until,
    )
    if src_ip:
        stmt = stmt.where(SecurityEvent.data["src_ip"].astext == src_ip)
    return int(db.scalar(stmt) or 0)


_INTERNAL_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
        "::1/128",
    )
]


def _is_external(ip: str | None) -> bool:
    """Anything outside the organisation's private address space counts as external."""
    try:
        addr = ipaddress.ip_address(str(ip))
    except ValueError:
        return False
    return not any(addr in net for net in _INTERNAL_NETS)


def detect(db: Session, asset_id, events: list[SecurityEvent]) -> list[Issue]:
    issues: dict[str, Issue] = {}
    for e in sorted(events, key=lambda x: x.occurred_at):
        data = e.data or {}
        if e.event_type == "network.config_change":
            issues["firewall_config_changed"] = Issue("firewall_config_changed", _evidence(e))
        elif e.event_type == "network.ids_alert":
            sev = data.get("suricata_severity")
            if sev == 1:
                issues["network_intrusion_alert"] = Issue("network_intrusion_alert", _evidence(e))
            elif sev == 2:
                issues.setdefault(
                    "suspicious_network_activity",
                    Issue("suspicious_network_activity", _evidence(e)),
                )
        elif e.event_type == "network.zeek_notice":
            note = str(data.get("note") or "")
            if note.startswith("Scan::"):
                issues["port_scan_detected"] = Issue("port_scan_detected", _evidence(e))
            elif note in _SUSPICIOUS_NOTICES:
                issues.setdefault(
                    "suspicious_network_activity",
                    Issue("suspicious_network_activity", _evidence(e)),
                )

    failures = [e for e in events if e.event_type == "network.admin_login_failure"]
    if failures:
        latest = max(e.occurred_at for e in failures)
        total = _count_in_window(db, asset_id, "network.admin_login_failure", latest)
        if total >= ADMIN_FAILURE_THRESHOLD:
            issues["network_admin_bruteforce"] = Issue(
                "network_admin_bruteforce",
                {
                    **_evidence(failures[-1]),
                    "failed_attempts": total,
                    "window_minutes": int(WINDOW.total_seconds() // 60),
                },
            )

    denies = [
        e
        for e in events
        if e.event_type == "network.firewall_deny" and _is_external((e.data or {}).get("src_ip"))
    ]
    for src in {(e.data or {}).get("src_ip") for e in denies}:
        latest = max(e.occurred_at for e in denies if (e.data or {}).get("src_ip") == src)
        total = _count_in_window(db, asset_id, "network.firewall_deny", latest, src)
        if total >= DENY_SCAN_THRESHOLD:
            issues["port_scan_detected"] = Issue(
                "port_scan_detected",
                {
                    "src_ip": src,
                    "blocked_connections": total,
                    "window_minutes": int(WINDOW.total_seconds() // 60),
                },
            )
    return list(issues.values())
