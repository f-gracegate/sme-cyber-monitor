import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import REFRESH_COOKIE, AuthContext, get_auth, get_auth_allow_pending
from app.core.config import settings
from app.core.db import get_db, set_tenant_context, system_context
from app.core.errors import APIError
from app.core.redis import rate_limit
from app.models import AuthSession, Invitation, Membership, Organisation, PasswordResetToken, User
from app.schemas.auth import (
    InvitationAcceptRequest,
    InvitationPreview,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MFACodeRequest,
    MFADisableRequest,
    MFAEnableResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RegisterRequest,
)
from app.schemas.common import Message
from app.security.passwords import (
    hash_password,
    needs_rehash,
    password_policy_errors,
    verify_password,
)
from app.security.rbac import ROLE_LABELS, Role
from app.security.tokens import (
    create_access_token,
    create_mfa_token,
    decode_token,
    encrypt_secret,
    hash_token,
    new_opaque_token,
)
from app.services import audit
from app.services.audit import client_ip
from app.services.auth import (
    build_me,
    clear_auth_cookies,
    find_user_by_identifier,
    generate_recovery_codes,
    revoke_user_sessions,
    set_auth_cookies,
    start_session,
    totp_uri,
    use_recovery_code,
    verify_totp,
)
from app.services.email import send_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

_INVALID_LOGIN = APIError(401, "invalid_credentials", "Incorrect email/username or password.")


def _policy_or_raise(password: str, email: str, username: str | None) -> None:
    errors = password_policy_errors(password, email=email, username=username or "")
    if errors:
        raise APIError(
            422,
            "weak_password",
            "Choose a stronger password.",
            [{"field": "password", "message": e} for e in errors],
        )


def _find_invitation(db: Session, token: str) -> Invitation | None:
    with system_context(db):
        return db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))


def _invitation_status(inv: Invitation) -> str:
    if inv.accepted_at:
        return "accepted"
    if inv.revoked_at:
        return "revoked"
    if inv.expires_at <= datetime.now(UTC):
        return "expired"
    return "pending"


def _accept_invitation(db: Session, user: User, inv: Invitation, request: Request) -> None:
    if _invitation_status(inv) != "pending":
        raise APIError(410, "invitation_unavailable", "This invitation is no longer valid.")
    if inv.email.lower() != user.email.lower():
        raise APIError(
            403,
            "invitation_email_mismatch",
            "This invitation was sent to a different email address.",
        )
    set_tenant_context(db, org=inv.organisation_id)
    existing = db.scalar(
        select(Membership).where(
            Membership.organisation_id == inv.organisation_id, Membership.user_id == user.id
        )
    )
    if existing is None:
        db.add(Membership(organisation_id=inv.organisation_id, user_id=user.id, role=inv.role))
    else:
        existing.role, existing.status = inv.role, "active"
    inv.accepted_at = datetime.now(UTC)
    audit.record(
        db,
        "member.joined",
        actor=user,
        organisation_id=inv.organisation_id,
        resource_type="membership",
        resource_id=user.id,
        details={"role": inv.role, "via": "invitation"},
        request=request,
    )


@router.post("/register", response_model=MeResponse, status_code=201)
def register(
    body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> MeResponse:
    rate_limit(f"register:{client_ip(request)}", limit=10, window_seconds=3600)
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise APIError(409, "email_taken", "An account with this email already exists.")
    if body.username and db.scalar(
        select(User.id).where(func.lower(User.username) == body.username.lower())
    ):
        raise APIError(409, "username_taken", "That username is already taken.")
    _policy_or_raise(body.password, email, body.username)

    invitation = _find_invitation(db, body.invitation_token) if body.invitation_token else None
    if body.invitation_token and invitation is None:
        raise APIError(404, "invitation_not_found", "Invitation not found.")

    user = User(
        email=email,
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        password_changed_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    set_tenant_context(db, user=user.id)
    audit.record(
        db,
        "user.registered",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    if invitation is not None:
        _accept_invitation(db, user, invitation, request)
    start_session(db, user, request, response)
    db.commit()
    return build_me(db, user)


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResponse:
    rate_limit(f"login-ip:{client_ip(request)}", limit=30, window_seconds=300)
    rate_limit(f"login-id:{body.identifier.strip().lower()}", limit=10, window_seconds=300)

    user = find_user_by_identifier(db, body.identifier)
    now = datetime.now(UTC)

    if user is not None and user.locked_until and user.locked_until > now:
        raise APIError(
            423,
            "account_locked",
            "Too many failed attempts. This account is temporarily locked. "
            "Try again later or reset your password.",
        )

    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:
            set_tenant_context(db, user=user.id)
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
            audit.record(
                db,
                "auth.login_failed",
                actor=user,
                resource_type="user",
                resource_id=user.id,
                request=request,
            )
            db.commit()
        raise _INVALID_LOGIN

    if user.status != "active":
        raise APIError(403, "account_inactive", "This account is not active.")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    set_tenant_context(db, user=user.id)
    if user.mfa_enabled:
        db.commit()
        return LoginResponse(status="mfa_required", mfa_token=create_mfa_token(user.id))

    start_session(db, user, request, response)
    audit.record(
        db, "auth.login", actor=user, resource_type="user", resource_id=user.id, request=request
    )
    db.commit()
    return LoginResponse(status="ok", me=build_me(db, user))


@router.post("/mfa/verify", response_model=LoginResponse)
def mfa_verify(
    body: MFAVerifyRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResponse:
    claims = decode_token(body.mfa_token, "mfa")
    if claims is None:
        raise APIError(401, "mfa_token_expired", "Your sign-in attempt expired. Sign in again.")
    rate_limit(f"mfa:{claims['sub']}", limit=10, window_seconds=300)
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.status != "active" or not user.mfa_enabled:
        raise APIError(401, "mfa_token_expired", "Your sign-in attempt expired. Sign in again.")

    set_tenant_context(db, user=user.id)
    used_recovery = False
    if not verify_totp(user, body.code):
        if not use_recovery_code(user, body.code):
            audit.record(
                db,
                "auth.mfa_failed",
                actor=user,
                resource_type="user",
                resource_id=user.id,
                request=request,
            )
            db.commit()
            raise APIError(401, "invalid_mfa_code", "That code is not valid. Try again.")
        used_recovery = True

    start_session(db, user, request, response)
    audit.record(
        db,
        "auth.login",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        details={"mfa": "recovery_code" if used_recovery else "totp"},
        request=request,
    )
    db.commit()
    return LoginResponse(status="ok", me=build_me(db, user))


@router.post("/refresh", response_model=Message)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> Message:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise APIError(401, "not_authenticated", "Please sign in to continue.")
    token_hash = hash_token(token)
    now = datetime.now(UTC)
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))

    if session is None:
        # A rotated-out token was presented again: treat the session as stolen and end it.
        reused = db.scalar(select(AuthSession).where(AuthSession.previous_token_hash == token_hash))
        if reused is not None and reused.revoked_at is None:
            reused.revoked_at, reused.revoked_reason = now, "refresh_token_reuse"
            user = db.get(User, reused.user_id)
            set_tenant_context(db, user=reused.user_id)
            audit.record(
                db,
                "auth.refresh_reuse_detected",
                actor=user,
                resource_type="session",
                resource_id=reused.id,
                request=request,
            )
            db.commit()
        clear_auth_cookies(response)
        raise APIError(401, "session_expired", "Please sign in again.")

    user = db.get(User, session.user_id)
    if session.revoked_at or session.expires_at <= now or user is None or user.status != "active":
        clear_auth_cookies(response)
        raise APIError(401, "session_expired", "Please sign in again.")

    new_token = new_opaque_token()
    session.previous_token_hash = token_hash
    session.refresh_token_hash = hash_token(new_token)
    session.last_used_at = now
    db.commit()
    set_auth_cookies(response, create_access_token(user.id, session.id), new_token)
    return Message(message="refreshed")


@router.post("/logout", response_model=Message)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_allow_pending),
    db: Session = Depends(get_db),
) -> Message:
    auth.session.revoked_at = datetime.now(UTC)
    auth.session.revoked_reason = "logout"
    audit.record(
        db,
        "auth.logout",
        actor=auth.user,
        resource_type="session",
        resource_id=auth.session.id,
        request=request,
    )
    db.commit()
    clear_auth_cookies(response)
    return Message(message="signed out")


@router.get("/me", response_model=MeResponse)
def me(
    auth: AuthContext = Depends(get_auth_allow_pending), db: Session = Depends(get_db)
) -> MeResponse:
    return build_me(db, auth.user)


@router.post("/password/change", response_model=Message)
def change_password(
    body: PasswordChangeRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_allow_pending),
    db: Session = Depends(get_db),
) -> Message:
    user = auth.user
    rate_limit(f"pwchange:{user.id}", limit=10, window_seconds=900)
    if not verify_password(body.current_password, user.password_hash):
        raise APIError(400, "invalid_current_password", "Your current password is incorrect.")
    if verify_password(body.new_password, user.password_hash):
        raise APIError(422, "password_reused", "Choose a password you have not just used.")
    _policy_or_raise(body.new_password, user.email, user.username)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = False
    revoke_user_sessions(db, user, "password_changed", except_session_id=auth.session.id)
    audit.record(
        db,
        "user.password_changed",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    db.commit()
    return Message(message="Password changed.")


@router.post("/password/forgot", response_model=Message, status_code=202)
def forgot_password(
    body: PasswordForgotRequest, request: Request, db: Session = Depends(get_db)
) -> Message:
    rate_limit(f"forgot-ip:{client_ip(request)}", limit=10, window_seconds=3600)
    rate_limit(f"forgot-email:{body.email.lower()}", limit=3, window_seconds=3600)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None and user.status == "active":
        token = new_opaque_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
        set_tenant_context(db, user=user.id)
        audit.record(
            db,
            "user.password_reset_requested",
            actor=user,
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        db.commit()
        link = f"{settings.web_base_url}/reset-password?token={token}"
        send_email(
            user.email,
            f"Reset your {settings.brand_product_name} password",
            f"Someone asked to reset your password.\n\nReset it here (valid for "
            f"{settings.password_reset_ttl_minutes} minutes):\n{link}\n\n"
            "If this wasn't you, you can ignore this email.",
        )
    # Same response whether or not the account exists.
    return Message(message="If an account exists for that email, we've sent a reset link.")


@router.post("/password/reset", response_model=Message)
def reset_password(
    body: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
) -> Message:
    rate_limit(f"reset-ip:{client_ip(request)}", limit=20, window_seconds=3600)
    now = datetime.now(UTC)
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token))
    )
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise APIError(400, "invalid_reset_token", "This reset link is invalid or has expired.")
    user = db.get(User, record.user_id)
    if user is None or user.status != "active":
        raise APIError(400, "invalid_reset_token", "This reset link is invalid or has expired.")
    _policy_or_raise(body.new_password, user.email, user.username)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = now
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    record.used_at = now
    revoke_user_sessions(db, user, "password_reset")
    set_tenant_context(db, user=user.id)
    audit.record(
        db,
        "user.password_reset",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    db.commit()
    return Message(message="Password reset. You can now sign in.")


@router.post("/mfa/setup", response_model=MFASetupResponse)
def mfa_setup(
    auth: AuthContext = Depends(get_auth_allow_pending), db: Session = Depends(get_db)
) -> MFASetupResponse:
    if auth.user.mfa_enabled:
        raise APIError(409, "mfa_already_enabled", "Multi-factor authentication is already on.")
    secret = pyotp.random_base32()
    auth.user.mfa_pending_secret_encrypted = encrypt_secret(secret)
    db.commit()
    return MFASetupResponse(secret=secret, otpauth_uri=totp_uri(secret, auth.user.email))


@router.post("/mfa/enable", response_model=MFAEnableResponse)
def mfa_enable(
    body: MFACodeRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_allow_pending),
    db: Session = Depends(get_db),
) -> MFAEnableResponse:
    user = auth.user
    rate_limit(f"mfa-enable:{user.id}", limit=10, window_seconds=300)
    if user.mfa_enabled:
        raise APIError(409, "mfa_already_enabled", "Multi-factor authentication is already on.")
    if not user.mfa_pending_secret_encrypted or not verify_totp(user, body.code, pending=True):
        raise APIError(400, "invalid_mfa_code", "That code is not valid. Try again.")
    codes, hashes = generate_recovery_codes()
    user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
    user.mfa_pending_secret_encrypted = None
    user.mfa_enabled = True
    user.mfa_recovery_code_hashes = hashes
    revoke_user_sessions(db, user, "mfa_enabled", except_session_id=auth.session.id)
    audit.record(
        db,
        "user.mfa_enabled",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    db.commit()
    return MFAEnableResponse(recovery_codes=codes)


@router.post("/mfa/disable", response_model=Message)
def mfa_disable(
    body: MFADisableRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> Message:
    user = auth.user
    rate_limit(f"mfa-disable:{user.id}", limit=10, window_seconds=300)
    if not user.mfa_enabled:
        raise APIError(409, "mfa_not_enabled", "Multi-factor authentication is not on.")
    if not verify_password(body.password, user.password_hash):
        raise APIError(400, "invalid_current_password", "Your password is incorrect.")
    if not verify_totp(user, body.code) and not use_recovery_code(user, body.code):
        raise APIError(400, "invalid_mfa_code", "That code is not valid. Try again.")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_recovery_code_hashes = []
    user.mfa_last_used_step = None
    audit.record(
        db,
        "user.mfa_disabled",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    db.commit()
    return Message(message="Multi-factor authentication turned off.")


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"invite-preview:{client_ip(request)}", limit=30, window_seconds=300)
    inv = _find_invitation(db, token)
    if inv is None:
        raise APIError(404, "invitation_not_found", "Invitation not found.")
    with system_context(db):
        org = db.get(Organisation, inv.organisation_id)
    account_exists = db.scalar(select(User.id).where(User.email == inv.email.lower())) is not None
    return InvitationPreview(
        organisation_name=org.name if org else "",
        email=inv.email,
        role=inv.role,
        role_label=ROLE_LABELS.get(Role(inv.role), inv.role),
        status=_invitation_status(inv),
        account_exists=account_exists,
    )


@router.post("/invitations/accept", response_model=MeResponse)
def accept_invitation(
    body: InvitationAcceptRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> MeResponse:
    inv = _find_invitation(db, body.token)
    if inv is None:
        raise APIError(404, "invitation_not_found", "Invitation not found.")
    _accept_invitation(db, auth.user, inv, request)
    db.commit()
    return build_me(db, auth.user)
