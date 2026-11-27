"""Network monitoring APIs: on-premises collectors and the network dashboard."""

import hashlib
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy import Integer, func, literal_column, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.api.v1.endpoints import (
    _INVALID_AGENT,
    _INVALID_TOKEN,
    _check_reenrolment,
    _limit_body,
    _send,
    check_collector_allowance,
    device_auth,
)
from app.billing.service import ensure_can_grow
from app.core.config import settings
from app.core.db import get_db, set_tenant_context, system_context
from app.core.errors import APIError
from app.core.redis import rate_limit
from app.endpoints import service as endpoint_service
from app.models import (
    Agent,
    AgentEnrolmentToken,
    Asset,
    Finding,
    MonitoringCheck,
    SecurityEvent,
    Subscription,
)
from app.monitoring.engine import RUNNABLE_ASSET_STATES
from app.network import service
from app.schemas.endpoint import AgentRelease, EventBatchResult
from app.schemas.network import (
    CollectorEnrol,
    CollectorEnrolResponse,
    CollectorHeartbeat,
    CollectorHeartbeatResponse,
    CollectorOut,
    NetworkDeviceOut,
    NetworkEventBatch,
    NetworkSummary,
    ProbeTarget,
    Signature,
)
from app.security.rbac import Perm
from app.security.tokens import hash_token, new_opaque_token
from app.services import audit
from app.services.audit import client_ip
from app.services.plans import get_plan

router = APIRouter()
COLLECTOR_VERSION = "1.0.0"


def collector_auth(agent: Agent = Depends(device_auth)) -> Agent:
    if agent.source != "collector":
        raise _INVALID_AGENT
    return agent


def _targets(db: Session, collector: Agent) -> list[ProbeTarget]:
    return [ProbeTarget(**t) for t in service.probe_targets(db, collector)]


# --- Collector-facing ----------------------------------------------------------------------


@router.post("/collector/enrol", response_model=CollectorEnrolResponse, tags=["Collector"])
def enrol_collector(
    body: CollectorEnrol, request: Request, db: Session = Depends(get_db)
) -> CollectorEnrolResponse:
    _limit_body(request, 65536)
    rate_limit(f"collector-enrol:{client_ip(request)}", limit=30, window_seconds=600)
    now = datetime.now(UTC)
    with system_context(db):
        token = db.scalar(
            select(AgentEnrolmentToken).where(
                AgentEnrolmentToken.token_hash == hash_token(body.token)
            )
        )
    if (
        token is None
        or token.kind != "collector"
        or token.revoked_at
        or token.expires_at <= now
        or token.uses >= token.max_uses
    ):
        raise _INVALID_TOKEN
    set_tenant_context(db, org=token.organisation_id)
    db.refresh(token, with_for_update=True)
    if token.uses >= token.max_uses:
        raise _INVALID_TOKEN
    ensure_can_grow(db, token.organisation_id)
    health = body.health.model_dump(mode="json")
    hostname = health["hostname"]

    collector = db.scalar(
        select(Agent).where(
            Agent.organisation_id == token.organisation_id,
            Agent.source == "collector",
            Agent.external_id == body.machine_id,
        )
    )
    if collector is None:
        check_collector_allowance(db, token.organisation_id)
        label = (body.name or hostname)[:180]
        asset = Asset(
            organisation_id=token.organisation_id,
            name=f"{label} (collector)",
            identifier=hostname[:500],
            type="network_device",
            department_id=token.department_id,
            created_by=token.created_by,
            technology=f"SMECM network collector {body.version}",
            criticality="high",
        )
        db.add(asset)
        db.flush()
        collector = Agent(
            organisation_id=token.organisation_id,
            asset_id=asset.id,
            source="collector",
            external_id=body.machine_id,
            hostname=hostname,
            enrolled_with=token.id,
        )
        db.add(collector)
        db.flush()
        endpoint_service.authorise_by_agent(
            db, asset, collector, {"agent": "collector", "hostname": hostname}
        )
    else:
        _check_reenrolment(collector)
        check_collector_allowance(db, token.organisation_id)
        collector.status, collector.revoked_at, collector.revoked_by = "active", None, None
    credential = new_opaque_token(32)
    collector.credential_hash = hash_token(credential)
    collector.enrolled_at = now
    collector.enrolled_with = token.id
    token.uses += 1
    audit.record(
        db,
        "network.collector_enrolled",
        organisation_id=token.organisation_id,
        actor_label=f"collector on {hostname}",
        resource_type="asset",
        resource_id=collector.asset_id,
        details={"hostname": hostname, "token": token.token_hint},
        request=request,
    )
    emails = service.process_heartbeat(
        db, collector, body.version, health, [], None, client_ip(request), now
    )
    targets = _targets(db, collector)
    db.commit()
    _send(emails)
    return CollectorEnrolResponse(
        collector_id=collector.id,
        credential=f"{collector.id}:{credential}",
        status="ok",
        heartbeat_seconds=service.HEARTBEAT_SECONDS,
        probe_seconds=service.PROBE_SECONDS,
        probe_targets=targets,
        server_time=now,
    )


@router.post("/collector/heartbeat", response_model=CollectorHeartbeatResponse, tags=["Collector"])
def collector_heartbeat(
    body: CollectorHeartbeat,
    request: Request,
    collector: Agent = Depends(collector_auth),
    db: Session = Depends(get_db),
) -> CollectorHeartbeatResponse:
    _limit_body(request, 512_000)
    rate_limit(f"collector-hb:{collector.id}", limit=30, window_seconds=300)
    emails = service.process_heartbeat(
        db,
        collector,
        body.version,
        body.health.model_dump(mode="json"),
        [p.model_dump() for p in body.probes],
        body.traffic.model_dump(mode="json") if body.traffic else None,
        client_ip(request),
    )
    targets = _targets(db, collector)
    db.commit()
    _send(emails)
    return CollectorHeartbeatResponse(
        status="ok",
        heartbeat_seconds=service.HEARTBEAT_SECONDS,
        probe_seconds=service.PROBE_SECONDS,
        probe_targets=targets,
        server_time=datetime.now(UTC),
    )


@router.post("/collector/events", response_model=EventBatchResult, tags=["Collector"])
def collector_events(
    body: NetworkEventBatch,
    request: Request,
    collector: Agent = Depends(collector_auth),
    db: Session = Depends(get_db),
) -> EventBatchResult:
    _limit_body(request, 2_000_000)
    rate_limit(f"collector-ev:{collector.id}", limit=600, window_seconds=300)
    accepted, duplicates, emails = service.ingest_network_events(
        db, collector, [e.model_dump() for e in body.events]
    )
    db.commit()
    _send(emails)
    return EventBatchResult(accepted=accepted, duplicates=duplicates)


def _collector_file() -> Path:
    return Path(settings.agent_dist_path).parent.parent / "network-collector" / "smecm_collector.py"


@router.get("/collector/release", response_model=AgentRelease, tags=["Collector"])
def collector_release() -> AgentRelease:
    path = _collector_file()
    if not path.is_file():
        raise APIError(404, "agent_unavailable", "The collector isn't available on this server.")
    content = path.read_bytes()
    return AgentRelease(
        version=COLLECTOR_VERSION,
        filename=path.name,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


@router.get("/collector/download", tags=["Collector"], response_class=FileResponse)
def collector_download() -> FileResponse:
    path = _collector_file()
    if not path.is_file():
        raise APIError(404, "agent_unavailable", "The collector isn't available on this server.")
    return FileResponse(path, media_type="text/x-python", filename=path.name)


# --- People-facing -------------------------------------------------------------------------


def _events_24h(db: Session, org_id, since: datetime):
    return select(SecurityEvent).where(
        SecurityEvent.organisation_id == org_id,
        SecurityEvent.event_type.like("network.%"),
        SecurityEvent.occurred_at >= since,
    )


@router.get("/network/collectors", response_model=list[CollectorOut], tags=["Network"])
def list_collectors(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)), db: Session = Depends(get_db)
) -> list[CollectorOut]:
    now = datetime.now(UTC)
    rows = db.execute(
        select(Agent, Asset)
        .join(Asset, Asset.id == Agent.asset_id)
        .where(
            Agent.organisation_id == ctx.org_id,
            Agent.source == "collector",
            Agent.status == "active",
            Asset.status == "active",
        )
        .order_by(Agent.hostname)
    ).all()
    out = []
    for agent, asset in rows:
        inv = agent.inventory or {}
        events = (
            db.scalar(
                select(func.count()).where(
                    SecurityEvent.agent_id == agent.id,
                    SecurityEvent.occurred_at >= now - timedelta(hours=24),
                )
            )
            or 0
        )
        out.append(
            CollectorOut(
                id=agent.id,
                asset_id=asset.id,
                name=asset.name,
                hostname=agent.hostname,
                version=agent.agent_version,
                status=agent.status,
                online=endpoint_service.is_online(agent, now),
                last_seen_at=agent.last_seen_at,
                last_ip=agent.last_ip,
                enrolled_at=agent.enrolled_at,
                capabilities=list(inv.get("capabilities") or []),
                sources=list(inv.get("sources") or []),
                queue_depth=inv.get("queue_depth"),
                events_24h=events,
                traffic=inv.get("traffic"),
            )
        )
    return out


@router.get("/network/devices", response_model=list[NetworkDeviceOut], tags=["Network"])
def list_devices(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)), db: Session = Depends(get_db)
) -> list[NetworkDeviceOut]:
    now = datetime.now(UTC)
    collectors = service.collector_asset_ids(db, ctx.org_id)
    rows = db.execute(
        select(Asset, MonitoringCheck)
        .outerjoin(
            MonitoringCheck,
            (MonitoringCheck.asset_id == Asset.id)
            & (MonitoringCheck.check_type == "device_availability"),
        )
        .where(
            Asset.organisation_id == ctx.org_id,
            Asset.status == "active",
            Asset.type.in_(service.NETWORK_TYPES),
        )
        .order_by(Asset.name)
    ).all()
    out = []
    for asset, check in rows:
        if asset.id in collectors:
            continue
        if asset.monitoring_status not in RUNNABLE_ASSET_STATES:
            availability = "awaiting_authorisation"
        elif check is None or check.last_run_at is None:
            availability = "not_probed"
        else:
            availability = "reachable" if check.last_status == "ok" else "unreachable"
        findings = (
            db.scalar(
                select(func.count()).where(Finding.asset_id == asset.id, Finding.status == "open")
            )
            or 0
        )
        events = (
            db.scalar(
                select(func.count()).where(
                    SecurityEvent.asset_id == asset.id,
                    SecurityEvent.occurred_at >= now - timedelta(hours=24),
                )
            )
            or 0
        )
        out.append(
            NetworkDeviceOut(
                id=asset.id,
                name=asset.name,
                identifier=asset.identifier,
                type=asset.type,
                criticality=asset.criticality,
                monitoring_status=asset.monitoring_status,
                availability=availability,
                latency_ms=(check.state or {}).get("latency_ms") if check else None,
                last_seen_at=asset.last_seen_at,
                last_checked_at=check.last_run_at if check else None,
                open_findings=findings,
                events_24h=events,
            )
        )
    return out


@router.get("/network/summary", response_model=NetworkSummary, tags=["Network"])
def network_summary(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)), db: Session = Depends(get_db)
) -> NetworkSummary:
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    collectors = list_collectors(ctx, db)
    devices = list_devices(ctx, db)
    availability = Counter(d.availability for d in devices)
    capabilities = {c for col in collectors for c in col.capabilities}
    events = _events_24h(db, ctx.org_id, since).subquery()
    ids = dict(
        db.execute(
            select(events.c.severity, func.count())
            .where(events.c.event_type == "network.ids_alert")
            .group_by(events.c.severity)
        ).all()
    )
    denies = (
        db.scalar(
            select(func.coalesce(func.sum(events.c.data["count"].astext.cast(Integer)), 0)).where(
                events.c.event_type == "network.firewall_deny"
            )
        )
        or 0
    )
    changes = (
        db.scalar(select(func.count()).where(events.c.event_type == "network.config_change")) or 0
    )
    # A literal JSON key, so SELECT and GROUP BY are the same expression to Postgres.
    signature = events.c.data.op("->>")(literal_column("'signature'"))
    signatures = db.execute(
        # Suricata severity: 1 is the most serious, so the minimum is the worst seen.
        select(
            signature,
            func.count(),
            func.min(events.c.data.op("->>")(literal_column("'suricata_severity'"))),
        )
        .where(events.c.event_type == "network.ids_alert")
        .group_by(signature)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    traffic = next((c.traffic for c in collectors if c.traffic), None)
    plan = get_plan(
        db.scalar(select(Subscription.plan_code).where(Subscription.organisation_id == ctx.org_id))
        or "starter"
    )
    return NetworkSummary(
        collectors_total=len(collectors),
        collectors_online=sum(1 for c in collectors if c.online),
        collector_allowance=plan.collector_limit,
        devices_total=len(devices),
        devices_reachable=availability.get("reachable", 0),
        devices_unreachable=availability.get("unreachable", 0),
        devices_not_probed=availability.get("not_probed", 0)
        + availability.get("awaiting_authorisation", 0),
        sensor_deployed=bool(capabilities & {"suricata", "zeek"}),
        ids_alerts_24h={k: ids.get(k, 0) for k in ("critical", "high", "medium", "low")},
        firewall_denies_24h=int(denies),
        config_changes_24h=changes,
        top_signatures=[
            Signature(
                name=name or "Unknown signature",
                count=n,
                severity={"1": "high", "2": "medium", "3": "low"}.get(sev or "", "medium"),
            )
            for name, n, sev in signatures
        ],
        traffic=traffic,
    )
