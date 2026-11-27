import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, OrgContext, get_auth, org_path_scope
from app.billing.service import ensure_can_grow
from app.core.config import settings
from app.core.db import get_db, set_tenant_context
from app.core.errors import APIError, forbidden, not_found
from app.core.redis import rate_limit
from app.models import Department, Invitation, Membership, Organisation, Subscription, User
from app.schemas.organisation import (
    DepartmentCreate,
    DepartmentOut,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    MemberOut,
    MemberUpdate,
    OrganisationCreate,
    OrganisationOut,
    OrganisationUpdate,
    OrganisationWithRole,
    RoleOut,
)
from app.security.rbac import ROLE_LABELS, Perm, Role, can_assign_role, permissions_for
from app.security.tokens import hash_token, new_opaque_token
from app.services import audit
from app.services.email import send_email
from app.services.plans import get_plan

router = APIRouter(tags=["Organisations"])


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: AuthContext = Depends(get_auth)) -> list[RoleOut]:
    return [
        RoleOut(value=r.value, label=ROLE_LABELS[r], permissions=sorted(permissions_for(r)))
        for r in Role
    ]


@router.get("/organisations", response_model=list[OrganisationWithRole])
def list_organisations(
    auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> list[OrganisationWithRole]:
    rows = db.execute(
        select(Organisation, Membership.role)
        .join(Membership, Membership.organisation_id == Organisation.id)
        .where(Membership.user_id == auth.user.id, Membership.status == "active")
        .order_by(Organisation.name)
    ).all()
    return [
        OrganisationWithRole(
            **OrganisationOut.model_validate(org).model_dump(),
            role=role,
            role_label=ROLE_LABELS[Role(role)],
        )
        for org, role in rows
    ]


@router.post("/organisations", response_model=OrganisationWithRole, status_code=201)
def create_organisation(
    body: OrganisationCreate,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> OrganisationWithRole:
    rate_limit(f"org-create:{auth.user.id}", limit=10, window_seconds=3600)
    org_id = uuid.uuid4()
    set_tenant_context(db, org=org_id)
    org = Organisation(id=org_id, created_by=auth.user.id, **body.model_dump())
    db.add(org)
    db.flush()
    db.add(Membership(organisation_id=org.id, user_id=auth.user.id, role=Role.OWNER))
    db.add(
        Subscription(
            organisation_id=org.id,
            plan_code="starter",
            status="trialing",
            current_period_end=datetime.now(UTC) + timedelta(days=14),
        )
    )
    audit.record(
        db,
        "organisation.created",
        actor=auth.user,
        organisation_id=org.id,
        resource_type="organisation",
        resource_id=org.id,
        details={"name": org.name},
        request=request,
    )
    db.commit()
    return OrganisationWithRole(
        **OrganisationOut.model_validate(org).model_dump(),
        role=Role.OWNER,
        role_label=ROLE_LABELS[Role.OWNER],
    )


@router.get("/organisations/{org_id}", response_model=OrganisationOut)
def get_organisation(ctx: OrgContext = Depends(org_path_scope(Perm.ORG_READ))) -> OrganisationOut:
    return OrganisationOut.model_validate(ctx.organisation)


@router.patch("/organisations/{org_id}", response_model=OrganisationOut)
def update_organisation(
    body: OrganisationUpdate,
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_UPDATE)),
    db: Session = Depends(get_db),
) -> OrganisationOut:
    org = ctx.organisation
    changes = body.model_dump(exclude_unset=True)
    if changes.get("require_mfa") and not ctx.user.mfa_enabled:
        raise APIError(
            409,
            "mfa_required_for_actor",
            "Turn on multi-factor authentication for your own account before requiring it "
            "for everyone.",
        )
    if "name" in changes and changes["name"] is None:
        changes.pop("name")
    for key, value in changes.items():
        setattr(org, key, value.strip() if isinstance(value, str) else value)
    audit.record(
        db,
        "organisation.updated",
        actor=ctx.user,
        organisation_id=org.id,
        resource_type="organisation",
        resource_id=org.id,
        details={"fields": sorted(changes)},
        request=ctx.request,
    )
    db.commit()
    return OrganisationOut.model_validate(org)


# --- Members -------------------------------------------------------------------------------


def _member_out(m: Membership, user: User, dept: Department | None, me: uuid.UUID) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=m.role,
        role_label=ROLE_LABELS[Role(m.role)],
        status=m.status,
        department_id=m.department_id,
        department_name=dept.name if dept else None,
        mfa_enabled=user.mfa_enabled,
        last_login_at=user.last_login_at,
        joined_at=m.created_at,
        is_you=user.id == me,
    )


@router.get("/organisations/{org_id}/members", response_model=list[MemberOut])
def list_members(
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_READ)), db: Session = Depends(get_db)
) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User, Department)
        .join(User, User.id == Membership.user_id)
        .outerjoin(Department, Department.id == Membership.department_id)
        .where(Membership.organisation_id == ctx.org_id)
        .order_by(User.full_name, User.email)
    ).all()
    return [_member_out(m, u, d, ctx.user.id) for m, u, d in rows]


def _active_owner_count(db: Session, org_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                Membership.organisation_id == org_id,
                Membership.role == Role.OWNER,
                Membership.status == "active",
            )
        )
        or 0
    )


def _get_member(db: Session, ctx: OrgContext, membership_id: uuid.UUID) -> Membership:
    m = db.get(Membership, membership_id)
    if m is None or m.organisation_id != ctx.org_id:
        raise not_found("Member")
    return m


@router.patch("/organisations/{org_id}/members/{membership_id}", response_model=MemberOut)
def update_member(
    membership_id: uuid.UUID,
    body: MemberUpdate,
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> MemberOut:
    m = _get_member(db, ctx, membership_id)
    details: dict = {}
    if m.user_id == ctx.user.id and (body.role or body.status):
        raise APIError(409, "cannot_change_self", "You cannot change your own role or status.")
    if not can_assign_role(ctx.role, m.role):
        raise forbidden("Only an owner can change another owner.")

    if body.role and body.role != m.role:
        if not can_assign_role(ctx.role, body.role):
            raise forbidden("Only an owner can grant the owner role.")
        if m.role == Role.OWNER and _active_owner_count(db, ctx.org_id) <= 1:
            raise APIError(409, "last_owner", "An organisation must keep at least one owner.")
        details["role"] = {"from": m.role, "to": body.role.value}
        m.role = body.role.value
    if body.status and body.status != m.status:
        if (
            body.status == "suspended"
            and m.role == Role.OWNER
            and _active_owner_count(db, ctx.org_id) <= 1
        ):
            raise APIError(409, "last_owner", "An organisation must keep at least one owner.")
        details["status"] = {"from": m.status, "to": body.status}
        m.status = body.status
    if body.clear_department:
        m.department_id = None
        details["department"] = None
    elif body.department_id:
        dept = db.get(Department, body.department_id)
        if dept is None or dept.organisation_id != ctx.org_id:
            raise not_found("Department")
        m.department_id = dept.id
        details["department"] = dept.name

    audit.record(
        db,
        "member.updated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="membership",
        resource_id=m.id,
        details=details,
        request=ctx.request,
    )
    db.commit()
    user = db.get(User, m.user_id)
    dept = db.get(Department, m.department_id) if m.department_id else None
    return _member_out(m, user, dept, ctx.user.id)


@router.delete("/organisations/{org_id}/members/{membership_id}", status_code=204)
def remove_member(
    membership_id: uuid.UUID,
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> Response:
    m = _get_member(db, ctx, membership_id)
    if m.user_id == ctx.user.id:
        raise APIError(409, "cannot_change_self", "You cannot remove yourself.")
    if not can_assign_role(ctx.role, m.role):
        raise forbidden("Only an owner can remove another owner.")
    if m.role == Role.OWNER and _active_owner_count(db, ctx.org_id) <= 1:
        raise APIError(409, "last_owner", "An organisation must keep at least one owner.")
    user = db.get(User, m.user_id)
    audit.record(
        db,
        "member.removed",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="membership",
        resource_id=m.id,
        details={"email": user.email if user else None, "role": m.role},
        request=ctx.request,
    )
    db.delete(m)
    db.commit()
    return Response(status_code=204)


# --- Invitations ---------------------------------------------------------------------------


def _pending_invitations(db: Session, org_id: uuid.UUID):
    return select(Invitation).where(
        Invitation.organisation_id == org_id,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
        Invitation.expires_at > datetime.now(UTC),
    )


@router.get("/organisations/{org_id}/invitations", response_model=list[InvitationOut])
def list_invitations(
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_READ)), db: Session = Depends(get_db)
) -> list[InvitationOut]:
    rows = db.execute(
        _pending_invitations(db, ctx.org_id)
        .add_columns(User.email)
        .outerjoin(User, User.id == Invitation.invited_by)
        .order_by(Invitation.created_at.desc())
    ).all()
    return [
        InvitationOut.model_validate(inv).model_copy(update={"invited_by_email": email})
        for inv, email in rows
    ]


@router.post(
    "/organisations/{org_id}/invitations", response_model=InvitationCreated, status_code=201
)
def create_invitation(
    body: InvitationCreate,
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    rate_limit(f"invite:{ctx.org_id}", limit=50, window_seconds=3600)
    ensure_can_grow(db, ctx.org_id)
    if not can_assign_role(ctx.role, body.role):
        raise forbidden("Only an owner can invite another owner.")
    email = body.email.lower()
    already = db.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organisation_id == ctx.org_id, User.email == email)
    )
    if already:
        raise APIError(409, "already_member", "This person is already a member.")

    plan = get_plan(_plan_code(db, ctx.org_id))
    if plan.member_limit is not None:
        members = (
            db.scalar(select(func.count()).where(Membership.organisation_id == ctx.org_id)) or 0
        )
        pending = (
            db.scalar(
                select(func.count()).select_from(_pending_invitations(db, ctx.org_id).subquery())
            )
            or 0
        )
        if members + pending >= plan.member_limit:
            raise APIError(
                402,
                "plan_limit_reached",
                f"Your {plan.name} plan allows {plan.member_limit} team members. "
                "Upgrade to invite more people.",
            )

    now = datetime.now(UTC)
    for old in db.scalars(_pending_invitations(db, ctx.org_id).where(Invitation.email == email)):
        old.revoked_at = now

    token = new_opaque_token()
    inv = Invitation(
        organisation_id=ctx.org_id,
        email=email,
        role=body.role.value,
        token_hash=hash_token(token),
        invited_by=ctx.user.id,
        expires_at=now + timedelta(days=settings.invitation_ttl_days),
    )
    db.add(inv)
    db.flush()
    audit.record(
        db,
        "member.invited",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"email": email, "role": inv.role},
        request=ctx.request,
    )
    db.commit()

    invite_url = f"{settings.web_base_url}/invite/{token}"
    send_email(
        email,
        f"You've been invited to {ctx.organisation.name}",
        f"{ctx.user.full_name or ctx.user.email} invited you to join {ctx.organisation.name} on "
        f"{settings.brand_product_name} as {ROLE_LABELS[body.role]}.\n\n"
        f"Accept the invitation (valid for {settings.invitation_ttl_days} days):\n{invite_url}",
    )
    return InvitationCreated(
        invitation=InvitationOut.model_validate(inv).model_copy(
            update={"invited_by_email": ctx.user.email}
        ),
        invite_url=invite_url,
    )


@router.delete("/organisations/{org_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: OrgContext = Depends(org_path_scope(Perm.MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> Response:
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.organisation_id != ctx.org_id:
        raise not_found("Invitation")
    if inv.revoked_at is None and inv.accepted_at is None:
        inv.revoked_at = datetime.now(UTC)
        audit.record(
            db,
            "member.invitation_revoked",
            actor=ctx.user,
            organisation_id=ctx.org_id,
            resource_type="invitation",
            resource_id=inv.id,
            details={"email": inv.email},
            request=ctx.request,
        )
        db.commit()
    return Response(status_code=204)


# --- Departments ---------------------------------------------------------------------------


@router.get("/organisations/{org_id}/departments", response_model=list[DepartmentOut])
def list_departments(
    ctx: OrgContext = Depends(org_path_scope(Perm.ORG_READ)), db: Session = Depends(get_db)
) -> list[DepartmentOut]:
    rows = db.scalars(
        select(Department).where(Department.organisation_id == ctx.org_id).order_by(Department.name)
    )
    return [DepartmentOut.model_validate(d) for d in rows]


@router.post("/organisations/{org_id}/departments", response_model=DepartmentOut, status_code=201)
def create_department(
    body: DepartmentCreate,
    ctx: OrgContext = Depends(org_path_scope(Perm.DEPARTMENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> DepartmentOut:
    dept = Department(organisation_id=ctx.org_id, name=body.name)
    db.add(dept)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "department_exists", "A department with that name exists.") from exc
    audit.record(
        db,
        "department.created",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="department",
        resource_id=dept.id,
        details={"name": dept.name},
        request=ctx.request,
    )
    db.commit()
    return DepartmentOut.model_validate(dept)


@router.delete("/organisations/{org_id}/departments/{department_id}", status_code=204)
def delete_department(
    department_id: uuid.UUID,
    ctx: OrgContext = Depends(org_path_scope(Perm.DEPARTMENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> Response:
    dept = db.get(Department, department_id)
    if dept is None or dept.organisation_id != ctx.org_id:
        raise not_found("Department")
    audit.record(
        db,
        "department.deleted",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="department",
        resource_id=dept.id,
        details={"name": dept.name},
        request=ctx.request,
    )
    db.delete(dept)
    db.commit()
    return Response(status_code=204)


def _plan_code(db: Session, org_id: uuid.UUID) -> str:
    return (
        db.scalar(select(Subscription.plan_code).where(Subscription.organisation_id == org_id))
        or "starter"
    )
