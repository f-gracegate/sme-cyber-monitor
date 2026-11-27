"""Data protection: retention settings, data export, organisation and account deletion."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, OrgContext, get_auth, org_path_scope
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import APIError, forbidden, not_found
from app.core.redis import rate_limit
from app.models import DataExport, Membership, Subscription, User
from app.privacy import service
from app.schemas.common import Message
from app.security.passwords import verify_password
from app.security.rbac import Perm, Role
from app.services import audit, storage
from app.services.email import send_email
from app.services.plans import get_plan

router = APIRouter(tags=["Data protection"])


class Retention(BaseModel):
    telemetry_retention_days: int = Field(ge=7, le=365)
    max_days: int | None = None


@router.get("/organisations/{org_id}/retention", response_model=Retention)
def get_retention(
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_READ)), db: Session = Depends(get_db)
) -> Retention:
    code = db.scalar(
        select(Subscription.plan_code).where(Subscription.organisation_id == ctx.org_id)
    )
    return Retention(
        telemetry_retention_days=ctx.organisation.telemetry_retention_days,
        max_days=get_plan(code or "starter").max_retention_days,
    )


@router.put("/organisations/{org_id}/retention", response_model=Retention)
def set_retention(
    body: Retention,
    request: Request,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> Retention:
    code = db.scalar(
        select(Subscription.plan_code).where(Subscription.organisation_id == ctx.org_id)
    )
    plan = get_plan(code or "starter")
    if body.telemetry_retention_days > plan.max_retention_days:
        raise APIError(
            422,
            "retention_above_plan",
            f"The {plan.name} plan keeps telemetry for up to {plan.max_retention_days} days.",
        )
    previous = ctx.organisation.telemetry_retention_days
    ctx.organisation.telemetry_retention_days = body.telemetry_retention_days
    audit.record(
        db,
        "organisation.retention_changed",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="organisation",
        resource_id=ctx.org_id,
        details={"from": previous, "to": body.telemetry_retention_days},
        request=request,
    )
    db.commit()
    return Retention(
        telemetry_retention_days=body.telemetry_retention_days, max_days=plan.max_retention_days
    )


# --- Export -----------------------------------------------------------------------------------


class ExportOut(BaseModel):
    id: uuid.UUID
    status: str
    size_bytes: int | None
    sha256: str | None
    summary: str | None
    requested_by_name: str | None
    created_at: datetime
    expires_at: datetime


def _owner_or_admin(ctx: OrgContext) -> None:
    if ctx.role not in {Role.OWNER, Role.ADMIN}:
        raise forbidden("Only owners and administrators can export or delete the organisation.")


def _export_out(db: Session, e: DataExport) -> ExportOut:
    user = db.get(User, e.requested_by) if e.requested_by else None
    return ExportOut(
        id=e.id,
        status=e.status,
        size_bytes=e.size_bytes,
        sha256=e.sha256,
        summary=e.summary,
        requested_by_name=(user.full_name or user.email) if user else None,
        created_at=e.created_at,
        expires_at=e.expires_at,
    )


@router.get("/organisations/{org_id}/exports", response_model=list[ExportOut])
def list_exports(
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)), db: Session = Depends(get_db)
) -> list[ExportOut]:
    _owner_or_admin(ctx)
    rows = db.scalars(
        select(DataExport)
        .where(DataExport.organisation_id == ctx.org_id)
        .order_by(DataExport.created_at.desc())
        .limit(20)
    )
    return [_export_out(db, e) for e in rows]


@router.post("/organisations/{org_id}/exports", response_model=ExportOut, status_code=201)
def create_export(
    request: Request,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> ExportOut:
    _owner_or_admin(ctx)
    rate_limit(f"export:{ctx.org_id}", limit=5, window_seconds=86400)
    export = service.create_export(db, ctx.organisation, ctx.user)
    audit.record(
        db,
        "organisation.data_exported",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="data_export",
        resource_id=export.id,
        details={"size_bytes": export.size_bytes},
        request=request,
    )
    db.commit()
    return _export_out(db, export)


@router.get("/organisations/{org_id}/exports/{export_id}/download")
def download_export(
    export_id: uuid.UUID,
    request: Request,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> Response:
    _owner_or_admin(ctx)
    export = db.get(DataExport, export_id)
    if export is None or export.organisation_id != ctx.org_id or export.status != "ready":
        raise not_found("Export")
    data = storage.get(ctx.org_id, export.storage_key)
    audit.record(
        db,
        "organisation.data_export_downloaded",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="data_export",
        resource_id=export.id,
        request=request,
    )
    db.commit()
    name = f"data-export-{export.created_at:%Y%m%d}.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- Organisation deletion --------------------------------------------------------------------


class DeletionRequest(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class DeletionStatus(BaseModel):
    scheduled_for: datetime | None
    requested_at: datetime | None


def _owners(db: Session, org_id: uuid.UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organisation_id == org_id,
                Membership.role == Role.OWNER,
                Membership.status == "active",
            )
        )
    )


@router.post("/organisations/{org_id}/deletion", response_model=DeletionStatus)
def request_deletion(
    body: DeletionRequest,
    request: Request,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> DeletionStatus:
    """Schedule erasure after a cooling-off period. Owners only, with password and name check."""
    if ctx.role != Role.OWNER:
        raise forbidden("Only an owner can delete the organisation.")
    rate_limit(f"org-delete:{ctx.user.id}", limit=5, window_seconds=3600)
    if not verify_password(body.password, ctx.user.password_hash):
        raise APIError(400, "invalid_current_password", "Your password is incorrect.")
    if body.confirm_name.strip() != ctx.organisation.name:
        raise APIError(422, "name_mismatch", "Type the organisation's name exactly to confirm.")
    org = ctx.organisation
    now = datetime.now(UTC)
    org.deletion_requested_at = now
    org.deletion_requested_by = ctx.user.id
    org.deletion_scheduled_for = now + timedelta(days=service.DELETION_GRACE_DAYS)
    audit.record(
        db,
        "organisation.deletion_requested",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="organisation",
        resource_id=ctx.org_id,
        details={"scheduled_for": org.deletion_scheduled_for.isoformat()},
        request=request,
    )
    db.commit()
    for owner in _owners(db, ctx.org_id):
        send_email(
            owner.email,
            f"{org.name} is scheduled for deletion",
            f"{ctx.user.full_name or ctx.user.email} asked for {org.name} to be deleted from "
            f"{settings.brand_product_name}.\n\nOn {org.deletion_scheduled_for:%d %B %Y} all of "
            "its assets, alerts, incidents, evidence, reports and monitoring data will be "
            "erased permanently. Download a data export before then if you need a copy.\n\n"
            f"Changed your mind? Cancel in Settings → Data and privacy: "
            f"{settings.web_base_url}/settings/privacy",
        )
    return DeletionStatus(
        scheduled_for=org.deletion_scheduled_for, requested_at=org.deletion_requested_at
    )


@router.delete("/organisations/{org_id}/deletion", response_model=DeletionStatus)
def cancel_deletion(
    request: Request,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> DeletionStatus:
    if ctx.role != Role.OWNER:
        raise forbidden("Only an owner can cancel the deletion.")
    org = ctx.organisation
    if org.deletion_scheduled_for is None:
        raise APIError(409, "not_scheduled", "This organisation isn't scheduled for deletion.")
    org.deletion_requested_at = org.deletion_requested_by = org.deletion_scheduled_for = None
    audit.record(
        db,
        "organisation.deletion_cancelled",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="organisation",
        resource_id=ctx.org_id,
        request=request,
    )
    db.commit()
    return DeletionStatus(scheduled_for=None, requested_at=None)


# --- Account deletion -------------------------------------------------------------------------


class AccountDeletion(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@router.post("/me/delete-account", response_model=Message)
def delete_account(
    body: AccountDeletion,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> Message:
    rate_limit(f"account-delete:{auth.user.id}", limit=5, window_seconds=3600)
    user = auth.user
    if not verify_password(body.password, user.password_hash):
        raise APIError(400, "invalid_current_password", "Your password is incorrect.")
    if user.is_platform_admin:
        raise APIError(409, "platform_admin", "Platform administrators can't delete themselves.")
    blocking = service.sole_owner_of(db, user)
    if blocking:
        raise APIError(
            409,
            "last_owner",
            "You're the only owner of "
            + ", ".join(blocking)
            + ". Make someone else an owner, or delete the organisation, first.",
        )
    audit.record(
        db,
        "user.account_deleted",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    service.anonymise_user(db, user)
    db.commit()
    return Message(message="Your account has been deleted.")
