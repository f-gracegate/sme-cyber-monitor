"""Request authentication and organisation (tenant) authorisation.

Every organisation-scoped endpoint resolves an :class:`OrgContext`, which:

1. authenticates the caller (cookie or bearer access token, backed by a live session row),
2. sets the PostgreSQL tenant context so Row-Level Security applies,
3. checks the caller holds an active membership in that organisation,
4. checks the specific permission the endpoint needs.

Access is decided here, on the server, never by what the interface chooses to show.
"""

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, set_tenant_context
from app.core.errors import APIError, forbidden
from app.models import AuthSession, Membership, Organisation, User
from app.security.rbac import Perm, permissions_for
from app.security.tokens import decode_token

ACCESS_COOKIE = "smecm_access"
REFRESH_COOKIE = "smecm_refresh"
CSRF_COOKIE = "smecm_csrf"
CSRF_HEADER = "x-csrf-token"
ORG_HEADER = "x-organisation-id"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class AuthContext:
    user: User
    session: AuthSession
    via_cookie: bool


def _unauthenticated(code: str = "not_authenticated") -> APIError:
    return APIError(401, code, "Please sign in to continue.")


def _authenticate(request: Request, db: Session, allow_pending_password: bool) -> AuthContext:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token, via_cookie = header[7:].strip(), False
    else:
        token, via_cookie = request.cookies.get(ACCESS_COOKIE), True
    if not token:
        raise _unauthenticated()

    claims = decode_token(token, "access")
    if claims is None:
        raise _unauthenticated("session_expired")

    if via_cookie and request.method in UNSAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        expected = request.cookies.get(CSRF_COOKIE, "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            raise APIError(403, "csrf_failed", "Security check failed. Refresh the page.")

    try:
        user_id = uuid.UUID(claims["sub"])
        session_id = uuid.UUID(claims["sid"])
    except (KeyError, ValueError) as exc:
        raise _unauthenticated() from exc

    session = db.get(AuthSession, session_id)
    now = datetime.now(UTC)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= now
    ):
        raise _unauthenticated("session_expired")

    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise _unauthenticated("account_inactive")

    set_tenant_context(db, user=user.id)

    if user.must_change_password and not allow_pending_password:
        raise APIError(
            403, "password_change_required", "You must change your password before continuing."
        )
    return AuthContext(user=user, session=session, via_cookie=via_cookie)


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    return _authenticate(request, db, allow_pending_password=False)


def get_auth_allow_pending(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """For the few endpoints a user may call before replacing a temporary password."""
    return _authenticate(request, db, allow_pending_password=True)


def require_platform_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth.user.is_platform_admin:
        raise forbidden()
    return auth


@dataclass
class OrgContext:
    user: User
    organisation: Organisation
    membership: Membership
    permissions: frozenset[Perm] = field(default_factory=frozenset)
    request: Request | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.organisation.id

    @property
    def role(self) -> str:
        return self.membership.role

    def has(self, perm: Perm) -> bool:
        return perm in self.permissions

    def require(self, perm: Perm) -> None:
        if perm not in self.permissions:
            raise forbidden()


def resolve_org(db: Session, auth: AuthContext, org_id: uuid.UUID, request: Request) -> OrgContext:
    set_tenant_context(db, org=org_id)
    membership = db.scalar(
        select(Membership).where(
            Membership.organisation_id == org_id, Membership.user_id == auth.user.id
        )
    )
    # Unknown organisations and organisations the user does not belong to look identical.
    if membership is None or membership.status != "active":
        raise APIError(404, "organisation_not_found", "Organisation not found.")
    organisation = db.get(Organisation, org_id)
    if organisation is None or organisation.deleted_at is not None:
        raise APIError(404, "organisation_not_found", "Organisation not found.")
    if organisation.status != "active":
        raise APIError(403, "organisation_suspended", "This organisation is suspended.")
    if organisation.require_mfa and not auth.user.mfa_enabled:
        raise APIError(
            403,
            "mfa_enrolment_required",
            "This organisation requires multi-factor authentication. Set it up to continue.",
        )
    return OrgContext(
        user=auth.user,
        organisation=organisation,
        membership=membership,
        permissions=permissions_for(membership.role),
        request=request,
    )


def _parse_org_header(value: str | None) -> uuid.UUID:
    if not value:
        raise APIError(400, "organisation_required", "Select an organisation first.")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise APIError(400, "organisation_required", "Invalid organisation identifier.") from exc


def org_scope(perm: Perm) -> Callable[..., OrgContext]:
    """Dependency for /api/v1/<resource> routes; the organisation comes from X-Organisation-Id."""

    def dependency(
        request: Request,
        x_organisation_id: str | None = Header(default=None),
        auth: AuthContext = Depends(get_auth),
        db: Session = Depends(get_db),
    ) -> OrgContext:
        ctx = resolve_org(db, auth, _parse_org_header(x_organisation_id), request)
        ctx.require(perm)
        return ctx

    return dependency


def org_path_scope(perm: Perm) -> Callable[..., OrgContext]:
    """Dependency for /api/v1/organisations/{org_id}/... routes."""

    def dependency(
        org_id: uuid.UUID,
        request: Request,
        auth: AuthContext = Depends(get_auth),
        db: Session = Depends(get_db),
    ) -> OrgContext:
        ctx = resolve_org(db, auth, org_id, request)
        ctx.require(perm)
        return ctx

    return dependency
