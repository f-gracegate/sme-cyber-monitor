"""Endpoint monitoring APIs.

Three audiences, three kinds of authentication:

* ``/agent/*``                      devices: short-lived enrolment token, then a device credential
* ``/integrations/wazuh/alerts``    a Wazuh manager: an organisation integration key
* ``/endpoints/*``, ``/integrations/keys``   people: session and role permissions
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.billing.service import ensure_can_grow
from app.core.config import settings
from app.core.db import get_db, set_tenant_context, system_context
from app.core.errors import APIError, not_found
from app.core.redis import rate_limit
from app.endpoints import service, wazuh
from app.models import (
    Agent,
    AgentEnrolmentToken,
    Alert,
    Asset,
    Department,
    Finding,
    IntegrationKey,
    SecurityEvent,
    Subscription,
)
from app.monitoring.engine import EmailJob
from app.schemas.common import Page
from app.schemas.endpoint import (
    AgentRelease,
    EndpointAsset,
    EndpointOut,
    EndpointSummary,
    EnrolRequest,
    EnrolResponse,
    EventBatch,
    EventBatchResult,
    HeartbeatRequest,
    HeartbeatResponse,
    IntegrationKeyCreate,
    IntegrationKeyCreated,
    IntegrationKeyOut,
    SecurityEventOut,
    TokenCreate,
    TokenCreated,
    TokenOut,
)
from app.security.rbac import Perm
from app.security.tokens import hash_token, new_opaque_token
from app.services import audit
from app.services.audit import client_ip
from app.services.email import send_email
from app.services.plans import get_plan


def _check_reenrolment(agent: Agent) -> None:
    """An enrolment token must never take over or revive an existing device on its own.

    Agents keep their credential and enrol only once, so a second enrolment for the same machine
    means a reinstall, a stolen token or an impersonation attempt. An administrator has to allow
    it first (revoke the device, then "Allow re-enrolment").
    """
    if agent.status == "reenrol_allowed":
        return
    if agent.status == "revoked":
        raise APIError(
            409,
            "device_revoked",
            "This device was removed by an administrator. Allow re-enrolment in the dashboard "
            "first.",
        )
    raise APIError(
        409,
        "already_enrolled",
        "This device is already enrolled. To reinstall, revoke it in the dashboard and allow "
        "re-enrolment.",
    )


def plan_limit_check(db: Session, org_id: uuid.UUID) -> None:
    """Refuse a new (or restored) asset when the plan's asset allowance is used up."""
    plan = get_plan(
        db.scalar(select(Subscription.plan_code).where(Subscription.organisation_id == org_id))
        or "starter"
    )
    if plan.asset_limit is None:
        return
    active = (
        db.scalar(
            select(func.count()).where(Asset.organisation_id == org_id, Asset.status == "active")
        )
        or 0
    )
    if active >= plan.asset_limit:
        raise APIError(
            402,
            "plan_limit_reached",
            f"This organisation's {plan.name} plan has no room for more assets.",
        )


def check_collector_allowance(db: Session, org_id: uuid.UUID) -> None:
    code = db.scalar(select(Subscription.plan_code).where(Subscription.organisation_id == org_id))
    plan = get_plan(code or "starter")
    if plan.collector_limit is None:
        return
    active = (
        db.scalar(
            select(func.count()).where(
                Agent.organisation_id == org_id,
                Agent.source == "collector",
                Agent.status == "active",
            )
        )
        or 0
    )
    if active >= plan.collector_limit:
        raise APIError(
            402,
            "plan_limit_reached",
            f"Your {plan.name} plan includes {plan.collector_limit} network collector(s). "
            "Network monitoring is part of the Professional plan and above.",
        )


router = APIRouter()

AGENT_VERSION = "1.0.0"
_INVALID_TOKEN = APIError(
    401, "invalid_enrolment_token", "This enrolment token is invalid, expired or used up."
)
_INVALID_AGENT = APIError(401, "invalid_agent_credential", "Agent credential not accepted.")


def _send(emails: list[EmailJob]) -> None:
    for job in emails:
        send_email(job.to, job.subject, job.body)


def _limit_body(request: Request, max_bytes: int) -> None:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise APIError(413, "payload_too_large", f"Request body must be under {max_bytes} bytes.")


# --- Device-facing -------------------------------------------------------------------------


def device_auth(
    request: Request,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Agent:
    """Authenticate a device by its credential and switch the DB context to its organisation."""
    scheme, _, value = authorization.partition(" ")
    agent_id, _, secret = value.partition(":")
    if scheme.lower() != "agent" or not secret:
        raise _INVALID_AGENT
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError as exc:
        raise _INVALID_AGENT from exc
    with system_context(db):
        agent = db.get(Agent, agent_uuid)
    if (
        agent is None
        or agent.status != "active"
        or not agent.credential_hash
        or not hmac.compare_digest(agent.credential_hash, hash_token(secret))
    ):
        raise _INVALID_AGENT
    set_tenant_context(db, org=agent.organisation_id)
    return agent


def agent_auth(agent: Agent = Depends(device_auth)) -> Agent:
    """Endpoint agents only (collectors use /collector/*)."""
    if agent.source != "smecm_agent":
        raise _INVALID_AGENT
    return agent


@router.post("/agent/enrol", response_model=EnrolResponse, tags=["Agent"])
def enrol(body: EnrolRequest, request: Request, db: Session = Depends(get_db)) -> EnrolResponse:
    _limit_body(request, 65536)
    rate_limit(f"agent-enrol:{client_ip(request)}", limit=120, window_seconds=600)
    now = datetime.now(UTC)
    with system_context(db):
        token = db.scalar(
            select(AgentEnrolmentToken).where(
                AgentEnrolmentToken.token_hash == hash_token(body.token)
            )
        )
    if (
        token is None
        or token.kind != "agent"
        or token.revoked_at
        or token.expires_at <= now
        or token.uses >= token.max_uses
    ):
        raise _INVALID_TOKEN
    set_tenant_context(db, org=token.organisation_id)
    # Lock the token so parallel enrolments can't exceed its allowed uses.
    db.refresh(token, with_for_update=True)
    if token.uses >= token.max_uses:
        raise _INVALID_TOKEN
    ensure_can_grow(db, token.organisation_id)
    inv = body.inventory.model_dump()

    agent = db.scalar(
        select(Agent).where(
            Agent.organisation_id == token.organisation_id,
            Agent.source == "smecm_agent",
            Agent.external_id == body.machine_id,
        )
    )
    if agent is None:
        plan_limit_check(db, token.organisation_id)
        asset = Asset(
            organisation_id=token.organisation_id,
            name=inv["hostname"][:200],
            identifier=inv["hostname"][:500],
            type=token.asset_type,
            department_id=token.department_id,
            created_by=token.created_by,
            technology=" ".join(p for p in (inv.get("os_name"), inv.get("os_version")) if p)
            or None,
        )
        db.add(asset)
        db.flush()
        agent = Agent(
            organisation_id=token.organisation_id,
            asset_id=asset.id,
            source="smecm_agent",
            external_id=body.machine_id,
            hostname=inv["hostname"],
            enrolled_with=token.id,
        )
        db.add(agent)
        db.flush()
        service.authorise_by_agent(
            db,
            asset,
            agent,
            {"agent": "smecm_agent", "hostname": inv["hostname"], "token": token.token_hint},
        )
    else:
        _check_reenrolment(agent)
        asset = db.get(Asset, agent.asset_id)
        if asset.status == "archived":
            plan_limit_check(db, token.organisation_id)
            asset.status = "active"
        agent.status, agent.revoked_at, agent.revoked_by = "active", None, None
    credential = new_opaque_token(32)
    agent.credential_hash = hash_token(credential)
    agent.enrolled_at = now
    agent.enrolled_with = token.id
    token.uses += 1
    audit.record(
        db,
        "endpoint.enrolled",
        organisation_id=token.organisation_id,
        actor_label=f"agent on {inv['hostname']}",
        resource_type="asset",
        resource_id=asset.id,
        details={"hostname": inv["hostname"], "token": token.token_hint},
        request=request,
    )
    emails = service.process_heartbeat(db, agent, inv, body.agent_version, client_ip(request), now)
    db.commit()
    _send(emails)
    return EnrolResponse(
        agent_id=agent.id,
        credential=f"{agent.id}:{credential}",
        heartbeat_seconds=service.HEARTBEAT_SECONDS,
        server_time=now,
    )


@router.post("/agent/heartbeat", response_model=HeartbeatResponse, tags=["Agent"])
def heartbeat(
    body: HeartbeatRequest,
    request: Request,
    agent: Agent = Depends(agent_auth),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    _limit_body(request, 65536)
    rate_limit(f"agent-hb:{agent.id}", limit=30, window_seconds=300)
    emails = service.process_heartbeat(
        db, agent, body.inventory.model_dump(), body.agent_version, client_ip(request)
    )
    db.commit()
    _send(emails)
    return HeartbeatResponse(
        status="ok", heartbeat_seconds=service.HEARTBEAT_SECONDS, server_time=datetime.now(UTC)
    )


@router.post("/agent/events", response_model=EventBatchResult, tags=["Agent"])
def events(
    body: EventBatch,
    request: Request,
    agent: Agent = Depends(agent_auth),
    db: Session = Depends(get_db),
) -> EventBatchResult:
    _limit_body(request, 2_000_000)
    rate_limit(f"agent-ev:{agent.id}", limit=120, window_seconds=300)
    accepted, duplicates, emails = service.ingest_events(
        db, agent, [e.model_dump() for e in body.events]
    )
    db.commit()
    _send(emails)
    return EventBatchResult(accepted=accepted, duplicates=duplicates)


def _agent_file() -> Path:
    return Path(settings.agent_dist_path)


@router.get("/agent/release", response_model=AgentRelease, tags=["Agent"])
def agent_release() -> AgentRelease:
    path = _agent_file()
    if not path.is_file():
        raise APIError(
            404, "agent_unavailable", "The agent package isn't available on this server."
        )
    content = path.read_bytes()
    return AgentRelease(
        version=AGENT_VERSION,
        filename=path.name,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


@router.get("/agent/download", tags=["Agent"], response_class=FileResponse)
def agent_download() -> FileResponse:
    path = _agent_file()
    if not path.is_file():
        raise APIError(
            404, "agent_unavailable", "The agent package isn't available on this server."
        )
    return FileResponse(path, media_type="text/x-python", filename=path.name)


@router.get("/agent/wazuh-integration", tags=["Agent"], response_class=FileResponse)
def wazuh_integration_script() -> FileResponse:
    """The forwarding script to install on a Wazuh manager (see Settings → Integrations)."""
    path = _agent_file().parent.parent / "wazuh" / "custom-smecm"
    if not path.is_file():
        raise APIError(404, "agent_unavailable", "The Wazuh integration script isn't available.")
    return FileResponse(path, media_type="text/x-python", filename="custom-smecm")


# --- Wazuh connector -----------------------------------------------------------------------


def _integration(db: Session, authorization: str, kind: str) -> IntegrationKey:
    scheme, _, key = authorization.partition(" ")
    parts = key.split("_")
    if scheme.lower() != "bearer" or len(parts) != 4 or parts[:2] != ["smecm", "int"]:
        raise APIError(401, "invalid_integration_key", "Integration key not accepted.")
    with system_context(db):
        record = db.scalar(select(IntegrationKey).where(IntegrationKey.key_prefix == parts[2]))
    if (
        record is None
        or record.revoked_at
        or record.kind != kind
        or not hmac.compare_digest(record.key_hash, hash_token(key))
    ):
        raise APIError(401, "invalid_integration_key", "Integration key not accepted.")
    return record


def _wazuh_agent(db: Session, org_id: uuid.UUID, identity: dict) -> Agent | None:
    agent = db.scalar(
        select(Agent).where(
            Agent.organisation_id == org_id,
            Agent.source == "wazuh",
            Agent.external_id == identity["id"],
        )
    )
    if agent is not None:
        return agent
    try:
        # New Wazuh machines count against the plan like any other asset.
        ensure_can_grow(db, org_id)
        plan_limit_check(db, org_id)
    except APIError:
        return None
    asset = Asset(
        organisation_id=org_id,
        name=identity["name"][:200],
        identifier=identity["name"][:500],
        type="server" if identity["id"] == "000" else "workstation",
        technology="Monitored by Wazuh",
    )
    db.add(asset)
    db.flush()
    agent = Agent(
        organisation_id=org_id,
        asset_id=asset.id,
        source="wazuh",
        external_id=identity["id"],
        hostname=identity["name"],
        last_ip=identity["ip"],
        agent_version="wazuh",
    )
    db.add(agent)
    db.flush()
    service.authorise_by_agent(
        db, asset, agent, {"agent": "wazuh", "wazuh_agent_id": identity["id"]}
    )
    asset.monitoring_status = "monitoring"
    return agent


@router.post("/integrations/wazuh/alerts", response_model=EventBatchResult, tags=["Integrations"])
def wazuh_alerts(
    request: Request,
    payload: dict = Body(...),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> EventBatchResult:
    """Receive one Wazuh alert, or ``{"alerts": [...]}`` with up to 100."""
    _limit_body(request, 2_000_000)
    key = _integration(db, authorization, "wazuh")
    rate_limit(f"wazuh:{key.id}", limit=600, window_seconds=60)
    set_tenant_context(db, org=key.organisation_id)
    alerts = payload.get("alerts") if isinstance(payload.get("alerts"), list) else [payload]
    if len(alerts) > 100:
        raise APIError(413, "payload_too_large", "Send at most 100 alerts per request.")

    by_agent: dict[str, tuple[dict, list[dict]]] = {}
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        identity = wazuh.agent_identity(alert)
        event = wazuh.map_alert(alert)
        if identity and event:
            by_agent.setdefault(identity["id"], (identity, []))[1].append(event)

    accepted = duplicates = 0
    emails: list[EmailJob] = []
    for identity, agent_events in by_agent.values():
        agent = _wazuh_agent(db, key.organisation_id, identity)
        if agent is None or agent.status != "active":
            continue
        a, d, e = service.ingest_events(db, agent, agent_events)
        accepted, duplicates, emails = accepted + a, duplicates + d, emails + e
    key.last_used_at = datetime.now(UTC)
    db.commit()
    _send(emails)
    return EventBatchResult(accepted=accepted, duplicates=duplicates)


@router.get("/integrations/keys", response_model=list[IntegrationKeyOut], tags=["Integrations"])
def list_keys(
    ctx: OrgContext = Depends(org_scope(Perm.ORG_UPDATE)), db: Session = Depends(get_db)
) -> list[IntegrationKeyOut]:
    rows = db.scalars(
        select(IntegrationKey)
        .where(IntegrationKey.organisation_id == ctx.org_id, IntegrationKey.revoked_at.is_(None))
        .order_by(IntegrationKey.created_at.desc())
    )
    return [IntegrationKeyOut.model_validate(k) for k in rows]


@router.post(
    "/integrations/keys",
    response_model=IntegrationKeyCreated,
    status_code=201,
    tags=["Integrations"],
)
def create_key(
    body: IntegrationKeyCreate,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> IntegrationKeyCreated:
    prefix = secrets.token_hex(6)
    key = f"smecm_int_{prefix}_{new_opaque_token(32).replace('_', '-')}"
    record = IntegrationKey(
        organisation_id=ctx.org_id,
        kind=body.kind,
        name=body.name.strip(),
        key_prefix=prefix,
        key_hash=hash_token(key),
        created_by=ctx.user.id,
    )
    db.add(record)
    db.flush()
    audit.record(
        db,
        "integration.key_created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="integration",
        resource_id=record.id,
        details={"kind": body.kind, "name": record.name},
        request=ctx.request,
    )
    db.commit()
    return IntegrationKeyCreated(key=key, details=IntegrationKeyOut.model_validate(record))


@router.delete("/integrations/keys/{key_id}", status_code=204, tags=["Integrations"])
def revoke_key(
    key_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> Response:
    record = db.get(IntegrationKey, key_id)
    if record is None or record.organisation_id != ctx.org_id:
        raise not_found("Integration key")
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        audit.record(
            db,
            "integration.key_revoked",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="integration",
            resource_id=record.id,
            details={"name": record.name},
            request=ctx.request,
        )
        db.commit()
    return Response(status_code=204)


# --- People-facing endpoint management -----------------------------------------------------


@router.post(
    "/endpoints/enrolment-tokens", response_model=TokenCreated, status_code=201, tags=["Endpoints"]
)
def create_token(
    body: TokenCreate,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> TokenCreated:
    ensure_can_grow(db, ctx.org_id)
    if body.department_id:
        dept = db.get(Department, body.department_id)
        if dept is None or dept.organisation_id != ctx.org_id:
            raise APIError(422, "validation_error", "Choose a department from this organisation.")
    if body.kind == "collector":
        check_collector_allowance(db, ctx.org_id)
    raw = f"{'col' if body.kind == 'collector' else 'enr'}_{new_opaque_token(24)}"
    token = AgentEnrolmentToken(
        organisation_id=ctx.org_id,
        kind=body.kind,
        token_hash=hash_token(raw),
        token_hint=raw[:10],
        label=(body.label or "").strip() or None,
        asset_type="network_device" if body.kind == "collector" else body.asset_type,
        department_id=body.department_id,
        max_uses=body.max_uses,
        created_by=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=body.valid_hours),
    )
    db.add(token)
    db.flush()
    audit.record(
        db,
        "endpoint.token_created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="enrolment_token",
        resource_id=token.id,
        details={
            "uses": body.max_uses,
            "valid_hours": body.valid_hours,
            "asset_type": body.asset_type,
        },
        request=ctx.request,
    )
    db.commit()
    return TokenCreated(token=raw, details=TokenOut.model_validate(token))


@router.get("/endpoints/enrolment-tokens", response_model=list[TokenOut], tags=["Endpoints"])
def list_tokens(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
    kind: Literal["agent", "collector"] = "agent",
) -> list[TokenOut]:
    rows = db.scalars(
        select(AgentEnrolmentToken)
        .where(
            AgentEnrolmentToken.organisation_id == ctx.org_id,
            AgentEnrolmentToken.kind == kind,
            AgentEnrolmentToken.revoked_at.is_(None),
            AgentEnrolmentToken.expires_at > datetime.now(UTC),
            AgentEnrolmentToken.uses < AgentEnrolmentToken.max_uses,
        )
        .order_by(AgentEnrolmentToken.created_at.desc())
    )
    return [TokenOut.model_validate(t) for t in rows]


@router.delete("/endpoints/enrolment-tokens/{token_id}", status_code=204, tags=["Endpoints"])
def revoke_token(
    token_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> Response:
    token = db.get(AgentEnrolmentToken, token_id)
    if token is None or token.organisation_id != ctx.org_id:
        raise not_found("Enrolment token")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        audit.record(
            db,
            "endpoint.token_revoked",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="enrolment_token",
            resource_id=token.id,
            request=ctx.request,
        )
        db.commit()
    return Response(status_code=204)


def _endpoint_out(
    db: Session, agent: Agent, asset: Asset, dept: Department | None, now: datetime
) -> EndpointOut:
    alerts = (
        db.scalar(
            select(func.count()).where(Alert.asset_id == asset.id, Alert.status != "resolved")
        )
        or 0
    )
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
    return EndpointOut(
        id=agent.id,
        source=agent.source,
        hostname=agent.hostname,
        os_family=agent.os_family,
        os_name=agent.os_name,
        os_version=agent.os_version,
        agent_version=agent.agent_version,
        status=agent.status,
        online=service.is_online(agent, now),
        last_seen_at=agent.last_seen_at,
        last_ip=agent.last_ip,
        enrolled_at=agent.enrolled_at,
        inventory=agent.inventory or {},
        asset=EndpointAsset(
            id=asset.id,
            name=asset.name,
            type=asset.type,
            department_name=dept.name if dept else None,
            criticality=asset.criticality,
        ),
        open_alerts=alerts,
        open_findings=findings,
        events_24h=events,
    )


@router.get("/endpoints", response_model=list[EndpointOut], tags=["Endpoints"])
def list_endpoints(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)),
    db: Session = Depends(get_db),
    asset_id: uuid.UUID | None = None,
    include_revoked: bool = False,
) -> list[EndpointOut]:
    stmt = (
        select(Agent, Asset, Department)
        .join(Asset, Asset.id == Agent.asset_id)
        .outerjoin(Department, Department.id == Asset.department_id)
        .where(
            Agent.organisation_id == ctx.org_id,
            Asset.status == "active",
            Agent.source != "collector",
        )
    )
    if asset_id:
        stmt = stmt.where(Agent.asset_id == asset_id)
    if not include_revoked:
        stmt = stmt.where(Agent.status == "active")
    now = datetime.now(UTC)
    rows = db.execute(stmt.order_by(Agent.hostname).limit(1000)).all()
    return [_endpoint_out(db, a, s, d, now) for a, s, d in rows]


@router.get("/endpoints/summary", response_model=EndpointSummary, tags=["Endpoints"])
def endpoint_summary(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)), db: Session = Depends(get_db)
) -> EndpointSummary:
    now = datetime.now(UTC)
    agents = list(
        db.scalars(
            select(Agent)
            .join(Asset, Asset.id == Agent.asset_id)
            .where(
                Agent.organisation_id == ctx.org_id,
                Agent.status == "active",
                Agent.source != "collector",
                Asset.status == "active",
            )
        )
    )
    online = sum(1 for a in agents if service.is_online(a, now))
    with_issues = (
        db.scalar(
            select(func.count(func.distinct(Finding.asset_id))).where(
                Finding.asset_id.in_([a.asset_id for a in agents]), Finding.status == "open"
            )
        )
        or 0
        if agents
        else 0
    )
    events = (
        db.scalar(
            select(func.count()).where(
                SecurityEvent.organisation_id == ctx.org_id,
                SecurityEvent.event_type.not_like("network.%"),
                SecurityEvent.occurred_at >= now - timedelta(hours=24),
            )
        )
        or 0
    )
    return EndpointSummary(
        total=len(agents),
        online=online,
        offline=len(agents) - online,
        with_issues=with_issues,
        events_24h=events,
    )


@router.post("/endpoints/{agent_id}/revoke", response_model=EndpointOut, tags=["Endpoints"])
def revoke_agent(
    agent_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> EndpointOut:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.organisation_id != ctx.org_id:
        raise not_found("Endpoint")
    if agent.status != "revoked":
        agent.status = "revoked"
        agent.revoked_at = datetime.now(UTC)
        agent.revoked_by = ctx.user.id
        agent.credential_hash = None
        audit.record(
            db,
            "endpoint.revoked",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="asset",
            resource_id=agent.asset_id,
            details={"hostname": agent.hostname},
            request=ctx.request,
        )
        db.commit()
    asset = db.get(Asset, agent.asset_id)
    dept = db.get(Department, asset.department_id) if asset.department_id else None
    return _endpoint_out(db, agent, asset, dept, datetime.now(UTC))


@router.post(
    "/endpoints/{agent_id}/allow-reenrolment", response_model=EndpointOut, tags=["Endpoints"]
)
def allow_reenrolment(
    agent_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_MANAGE)),
    db: Session = Depends(get_db),
) -> EndpointOut:
    """Let a revoked device enrol once more (for example after reinstalling the agent)."""
    agent = db.get(Agent, agent_id)
    if agent is None or agent.organisation_id != ctx.org_id:
        raise not_found("Endpoint")
    if agent.status != "revoked":
        raise APIError(409, "not_revoked", "Only a revoked device can be allowed to enrol again.")
    agent.status = "reenrol_allowed"
    audit.record(
        db,
        "endpoint.reenrolment_allowed",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=agent.asset_id,
        details={"hostname": agent.hostname},
        request=ctx.request,
    )
    db.commit()
    asset = db.get(Asset, agent.asset_id)
    dept = db.get(Department, asset.department_id) if asset.department_id else None
    return _endpoint_out(db, agent, asset, dept, datetime.now(UTC))


@router.get("/endpoints/events", response_model=Page[SecurityEventOut], tags=["Endpoints"])
def list_events(
    ctx: OrgContext = Depends(org_scope(Perm.MONITORING_READ)),
    db: Session = Depends(get_db),
    asset_id: uuid.UUID | None = None,
    event_type: str | None = None,
    category: Literal["endpoint", "network"] | None = None,
    severity: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[SecurityEventOut]:
    stmt = (
        select(SecurityEvent, Asset.name)
        .join(Asset, Asset.id == SecurityEvent.asset_id)
        .where(SecurityEvent.organisation_id == ctx.org_id)
    )
    if asset_id:
        stmt = stmt.where(SecurityEvent.asset_id == asset_id)
    if event_type:
        stmt = stmt.where(SecurityEvent.event_type == event_type)
    if category == "network":
        stmt = stmt.where(SecurityEvent.event_type.like("network.%"))
    elif category == "endpoint":
        stmt = stmt.where(SecurityEvent.event_type.not_like("network.%"))
    if severity:
        stmt = stmt.where(SecurityEvent.severity.in_(severity))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(SecurityEvent.occurred_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[SecurityEventOut](
        items=[
            SecurityEventOut.model_validate(e).model_copy(update={"asset_name": n}) for e, n in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
