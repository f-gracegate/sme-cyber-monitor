import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import Request, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.core.config import settings
from app.models import AuthSession, Membership, Organisation, User
from app.schemas.auth import MembershipSummary, MeResponse, TokenPair, UserOut
from app.security.passwords import hash_password, verify_password
from app.security.rbac import ROLE_LABELS, Role, permissions_for
from app.security.tokens import (
    create_access_token,
    decrypt_secret,
    hash_token,
    new_opaque_token,
)
from app.services.audit import client_ip

REFRESH_COOKIE_PATH = "/api/v1/auth"
MFA_ISSUER = "SME Cybersecurity Monitoring"


def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    return db.scalar(
        select(User).where(or_(User.email == ident, func.lower(User.username) == ident))
    )


def start_session(
    db: Session, user: User, request: Request, response: Response, client: str = "web"
) -> TokenPair | None:
    """Create a session and record the sign-in.

    Web sessions get httpOnly cookies. Mobile sessions get the tokens back (for the app's
    secure storage) and no cookies.
    """
    refresh_token = new_opaque_token()
    now = datetime.now(UTC)
    ttl_days = (
        settings.mobile_refresh_token_ttl_days
        if client == "mobile"
        else settings.refresh_token_ttl_days
    )
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        expires_at=now + timedelta(days=ttl_days),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        ip_address=client_ip(request),
        client=client,
    )
    db.add(session)
    user.last_login_at = now
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    access = create_access_token(user.id, session.id)
    if client == "mobile":
        return token_pair(access, refresh_token)
    set_auth_cookies(response, access, refresh_token)
    return None


def token_pair(access_token: str, refresh_token: str) -> TokenPair:
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {"secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        path="/",
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        path=REFRESH_COOKIE_PATH,
        **common,
    )
    # Readable by the web app so it can echo it in the X-CSRF-Token header (double submit).
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=False,
        path="/",
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def revoke_user_sessions(db: Session, user: User, reason: str, except_session_id=None) -> None:
    stmt = (
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    if except_session_id is not None:
        stmt = stmt.where(AuthSession.id != except_session_id)
    db.execute(stmt)


def build_me(db: Session, user: User) -> MeResponse:
    rows = db.execute(
        select(Membership, Organisation)
        .join(Organisation, Organisation.id == Membership.organisation_id)
        .where(Membership.user_id == user.id, Membership.status == "active")
        .order_by(Organisation.name)
    ).all()
    memberships = [
        MembershipSummary(
            organisation_id=org.id,
            organisation_name=org.name,
            role=m.role,
            role_label=ROLE_LABELS.get(Role(m.role), m.role),
            permissions=sorted(p.value for p in permissions_for(m.role)),
            require_mfa=org.require_mfa,
        )
        for m, org in rows
        if org.status == "active"
    ]
    return MeResponse(user=UserOut.model_validate(user), memberships=memberships)


def verify_totp(user: User, code: str, *, pending: bool = False) -> bool:
    """Check a TOTP code, rejecting a code that has already been used (replay)."""
    encrypted = user.mfa_pending_secret_encrypted if pending else user.mfa_secret_encrypted
    secret = decrypt_secret(encrypted) if encrypted else None
    code = code.strip().replace(" ", "")
    if not secret or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    for offset in (-1, 0, 1):
        at = now + timedelta(seconds=30 * offset)
        if totp.verify(code, for_time=at, valid_window=0):
            step = int(at.timestamp()) // 30
            if user.mfa_last_used_step is not None and step <= user.mfa_last_used_step:
                return False
            user.mfa_last_used_step = step
            return True
    return False


def use_recovery_code(user: User, code: str) -> bool:
    normalised = code.strip().replace("-", "").replace(" ", "").lower()
    for stored in list(user.mfa_recovery_code_hashes or []):
        if verify_password(normalised, stored):
            user.mfa_recovery_code_hashes = [
                h for h in user.mfa_recovery_code_hashes if h != stored
            ]
            return True
    return False


def generate_recovery_codes(count: int = 10) -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(count)]
    hashes = [hash_password(c.replace("-", "")) for c in codes]
    return codes, hashes


def totp_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=MFA_ISSUER)
