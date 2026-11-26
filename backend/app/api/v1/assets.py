import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.core.db import get_db
from app.core.errors import APIError, not_found
from app.core.redis import rate_limit
from app.models import (
    Asset,
    AssetAuthorisation,
    AuditLog,
    Department,
    Membership,
    Subscription,
    User,
)
from app.models.asset import ASSET_CATEGORIES, EXTERNAL_ASSET_TYPES
from app.schemas.asset import (
    AssetCreate,
    AssetDetail,
    AssetOut,
    AssetUpdate,
    AuditEntryOut,
    AuthorisationOut,
    VerificationInstructions,
    VerificationStart,
    normalise_identifier,
)
from app.schemas.common import Page
from app.security.rbac import Perm
from app.services import audit, verification
from app.services.plans import get_plan

router = APIRouter(prefix="/assets", tags=["Assets"])

SORTS = {
    "name": Asset.name,
    "created_at": Asset.created_at,
    "type": Asset.type,
    "criticality": Asset.criticality,
    "last_seen_at": Asset.last_seen_at,
}


def _asset_out(asset: Asset, dept: Department | None, owner: User | None) -> AssetOut:
    return AssetOut.model_validate(asset).model_copy(
        update={
            "category": ASSET_CATEGORIES.get(asset.type, "other"),
            "department_name": dept.name if dept else None,
            "owner_name": (owner.full_name or owner.email) if owner else None,
        }
    )


def _load(db: Session, ctx: OrgContext, asset_id: uuid.UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.organisation_id != ctx.org_id:
        raise not_found("Asset")
    return asset


def _latest_authorisation(db: Session, asset: Asset) -> AssetAuthorisation | None:
    return db.scalar(
        select(AssetAuthorisation)
        .where(
            AssetAuthorisation.asset_id == asset.id,
            AssetAuthorisation.status != "superseded",
        )
        .order_by(AssetAuthorisation.created_at.desc())
        .limit(1)
    )


def _methods_for(asset: Asset) -> list[str]:
    return ["dns_txt", "http_file"] if asset.type in EXTERNAL_ASSET_TYPES else ["attestation"]


def _detail(db: Session, asset: Asset) -> AssetDetail:
    dept = db.get(Department, asset.department_id) if asset.department_id else None
    owner = db.get(User, asset.owner_user_id) if asset.owner_user_id else None
    auth = _latest_authorisation(db, asset)
    instr = (
        VerificationInstructions(**verification.instructions(asset, auth.method, auth.challenge))
        if auth
        else None
    )
    return AssetDetail(
        **_asset_out(asset, dept, owner).model_dump(),
        authorisation=AuthorisationOut.model_validate(auth) if auth else None,
        instructions=instr,
        verification_methods=_methods_for(asset),
    )


def _check_refs(db: Session, ctx: OrgContext, department_id, owner_user_id) -> None:
    if department_id:
        dept = db.get(Department, department_id)
        if dept is None or dept.organisation_id != ctx.org_id:
            raise APIError(
                422,
                "validation_error",
                "Choose a department from this organisation.",
                [{"field": "department_id", "message": "Unknown department."}],
            )
    if owner_user_id:
        member = db.scalar(
            select(Membership.id).where(
                Membership.organisation_id == ctx.org_id, Membership.user_id == owner_user_id
            )
        )
        if member is None:
            raise APIError(
                422,
                "validation_error",
                "The owner must be a team member.",
                [{"field": "owner_user_id", "message": "Unknown team member."}],
            )


def _ensure_unique(
    db: Session, ctx: OrgContext, asset_type: str, identifier: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(Asset.id).where(
        Asset.organisation_id == ctx.org_id,
        Asset.type == asset_type,
        func.lower(Asset.identifier) == identifier.lower(),
        Asset.status == "active",
    )
    if exclude:
        stmt = stmt.where(Asset.id != exclude)
    if db.scalar(stmt):
        raise APIError(409, "asset_exists", "An asset with this identifier is already registered.")


@router.get("", response_model=Page[AssetOut])
def list_assets(
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_READ)),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200),
    type: list[str] | None = Query(default=None),
    category: str | None = None,
    monitoring_status: str | None = None,
    criticality: str | None = None,
    department_id: uuid.UUID | None = None,
    status: Literal["active", "archived"] = "active",
    sort: str = "name",
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[AssetOut]:
    stmt = select(Asset).where(Asset.organisation_id == ctx.org_id, Asset.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.name.ilike(like), Asset.identifier.ilike(like)))
    types = set(type or [])
    if category:
        types |= {t for t, c in ASSET_CATEGORIES.items() if c == category} or {"__none__"}
    if types:
        stmt = stmt.where(Asset.type.in_(types))
    if monitoring_status:
        stmt = stmt.where(Asset.monitoring_status == monitoring_status)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
    if department_id:
        stmt = stmt.where(Asset.department_id == department_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTS.get(sort, Asset.name)
    ordered = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    rows = db.execute(
        stmt.add_columns(Department, User)
        .outerjoin(Department, Department.id == Asset.department_id)
        .outerjoin(User, User.id == Asset.owner_user_id)
        .order_by(ordered, Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[AssetOut](
        items=[_asset_out(a, d, u) for a, d, u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=AssetDetail, status_code=201)
def create_asset(
    body: AssetCreate,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_WRITE)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    plan_code = db.scalar(
        select(Subscription.plan_code).where(Subscription.organisation_id == ctx.org_id)
    )
    plan = get_plan(plan_code or "starter")
    if plan.asset_limit is not None:
        active = (
            db.scalar(
                select(func.count()).where(
                    Asset.organisation_id == ctx.org_id, Asset.status == "active"
                )
            )
            or 0
        )
        if active >= plan.asset_limit:
            raise APIError(
                402,
                "plan_limit_reached",
                f"Your {plan.name} plan includes {plan.asset_limit} assets. "
                "Archive an asset or upgrade to add more.",
            )
    _check_refs(db, ctx, body.department_id, body.owner_user_id)
    _ensure_unique(db, ctx, body.type, body.identifier)
    asset = Asset(organisation_id=ctx.org_id, created_by=ctx.user.id, **body.model_dump())
    db.add(asset)
    db.flush()
    audit.record(
        db,
        "asset.created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=asset.id,
        details={"name": asset.name, "type": asset.type, "identifier": asset.identifier},
        request=ctx.request,
    )
    db.commit()
    return _detail(db, asset)


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_READ)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    return _detail(db, _load(db, ctx, asset_id))


@router.patch("/{asset_id}", response_model=AssetDetail)
def update_asset(
    asset_id: uuid.UUID,
    body: AssetUpdate,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_WRITE)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset = _load(db, ctx, asset_id)
    if asset.status != "active":
        raise APIError(409, "asset_archived", "Restore this asset before editing it.")
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "identifier", "criticality"):
        if required in changes and changes[required] is None:
            changes.pop(required)
    _check_refs(db, ctx, changes.get("department_id"), changes.get("owner_user_id"))

    if "identifier" in changes:
        try:
            new_identifier = normalise_identifier(asset.type, changes["identifier"])
        except ValueError as exc:
            raise APIError(
                422, "validation_error", str(exc), [{"field": "identifier", "message": str(exc)}]
            ) from exc
        if new_identifier == asset.identifier:
            changes.pop("identifier")
        else:
            _ensure_unique(db, ctx, asset.type, new_identifier, exclude=asset.id)
            changes["identifier"] = new_identifier
            # Proof of control was for the old identifier; it no longer counts.
            for auth in db.scalars(
                select(AssetAuthorisation).where(
                    AssetAuthorisation.asset_id == asset.id,
                    AssetAuthorisation.status != "superseded",
                )
            ):
                auth.status = "superseded"
            asset.monitoring_status = "not_monitored"

    for key in ("name", "technology", "location", "notes"):
        if isinstance(changes.get(key), str):
            changes[key] = changes[key].strip() or (None if key != "name" else asset.name)
    before = {k: getattr(asset, k) for k in changes}
    for key, value in changes.items():
        setattr(asset, key, value)
    audit.record(
        db,
        "asset.updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=asset.id,
        details={
            "changes": {
                k: {
                    "from": str(before[k]) if before[k] is not None else None,
                    "to": str(v) if v is not None else None,
                }
                for k, v in changes.items()
                if before[k] != v
            }
        },
        request=ctx.request,
    )
    db.commit()
    return _detail(db, asset)


@router.post("/{asset_id}/archive", response_model=AssetDetail)
def archive_asset(
    asset_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_WRITE)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset = _load(db, ctx, asset_id)
    if asset.status != "archived":
        asset.status = "archived"
        asset.monitoring_status = (
            "paused" if asset.monitoring_status != "not_monitored" else asset.monitoring_status
        )
        audit.record(
            db,
            "asset.archived",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="asset",
            resource_id=asset.id,
            request=ctx.request,
        )
        db.commit()
    return _detail(db, asset)


@router.post("/{asset_id}/restore", response_model=AssetDetail)
def restore_asset(
    asset_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_WRITE)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset = _load(db, ctx, asset_id)
    if asset.status == "archived":
        _ensure_unique(db, ctx, asset.type, asset.identifier, exclude=asset.id)
        asset.status = "active"
        if asset.monitoring_status == "paused":
            asset.monitoring_status = "authorised"
        audit.record(
            db,
            "asset.restored",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="asset",
            resource_id=asset.id,
            request=ctx.request,
        )
        db.commit()
    return _detail(db, asset)


@router.post("/{asset_id}/verification", response_model=AssetDetail)
def start_verification(
    asset_id: uuid.UUID,
    body: VerificationStart,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_VERIFY)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    """Begin proving authorisation. Websites and domains need technical proof of control;
    internal assets are confirmed by an administrator and later by agent enrolment."""
    asset = _load(db, ctx, asset_id)
    if asset.status != "active":
        raise APIError(409, "asset_archived", "Restore this asset first.")
    if body.method not in _methods_for(asset):
        raise APIError(
            422,
            "method_not_allowed",
            "Websites and domains must be verified with a DNS record or a verification file."
            if asset.type in EXTERNAL_ASSET_TYPES
            else "Internal assets are authorised by administrator confirmation.",
        )
    if body.method == "attestation" and not (body.statement and body.statement.strip()):
        raise APIError(
            422,
            "validation_error",
            "Describe why you are authorised.",
            [{"field": "statement", "message": "Required."}],
        )

    now = datetime.now(UTC)
    for old in db.scalars(
        select(AssetAuthorisation).where(
            AssetAuthorisation.asset_id == asset.id, AssetAuthorisation.status != "superseded"
        )
    ):
        old.status = "superseded"

    auth = AssetAuthorisation(
        organisation_id=ctx.org_id,
        asset_id=asset.id,
        method=body.method,
        challenge=verification.new_challenge(),
        requested_by=ctx.user.id,
    )
    if body.method == "attestation":
        auth.status = "verified"
        auth.verified_at = now
        auth.verified_by = ctx.user.id
        auth.evidence = {"statement": body.statement.strip(), "attested_by": ctx.user.email}
        asset.monitoring_status = "authorised"
        action = "asset.authorised"
    else:
        asset.monitoring_status = "not_monitored"
        action = "asset.verification_started"
    db.add(auth)
    db.flush()
    audit.record(
        db,
        action,
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=asset.id,
        details={"method": body.method},
        request=ctx.request,
    )
    db.commit()
    return _detail(db, asset)


@router.post("/{asset_id}/verify", response_model=AssetDetail)
def check_verification(
    asset_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_VERIFY)),
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset = _load(db, ctx, asset_id)
    auth = _latest_authorisation(db, asset)
    if auth is None or auth.method == "attestation":
        raise APIError(409, "no_pending_verification", "Start verification first.")
    if auth.status == "verified":
        return _detail(db, asset)
    rate_limit(f"verify:{asset.id}", limit=10, window_seconds=300)

    host = verification.asset_hostname(asset)
    checker = (
        verification.check_dns_txt if auth.method == "dns_txt" else verification.check_http_file
    )
    result = checker(host, auth.challenge)
    now = datetime.now(UTC)
    auth.last_attempt_at = now
    auth.evidence = result.evidence
    if result.ok:
        auth.status = "verified"
        auth.verified_at = now
        auth.verified_by = ctx.user.id
        auth.failure_reason = None
        asset.monitoring_status = "authorised"
        action = "asset.authorised"
    else:
        auth.status = "failed"
        auth.failure_reason = result.detail[:300]
        action = "asset.verification_failed"
    audit.record(
        db,
        action,
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="asset",
        resource_id=asset.id,
        details={"method": auth.method, "detail": result.detail},
        request=ctx.request,
    )
    db.commit()
    return _detail(db, asset)


@router.get("/{asset_id}/activity", response_model=Page[AuditEntryOut])
def asset_activity(
    asset_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.ASSETS_READ)),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[AuditEntryOut]:
    asset = _load(db, ctx, asset_id)
    stmt = select(AuditLog).where(
        AuditLog.organisation_id == ctx.org_id,
        AuditLog.resource_type == "asset",
        AuditLog.resource_id == str(asset.id),
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[AuditEntryOut](
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
