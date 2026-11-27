import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    """A person who can sign in. Users are global; organisation access comes from memberships."""

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_username_lower", text("lower(username)"), unique=True),)

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # active | suspended | disabled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set once the person proves they own the address (verification link, invitation or reset).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    mfa_recovery_code_hashes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mfa_last_used_step: Mapped[int | None] = mapped_column(Integer)

    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(UUIDPrimaryKey, Base):
    """A signed-in browser or device. Holds the hashed, rotating refresh token."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Hash of the token this one replaced, so reuse of a rotated token can be detected.
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    # web (httpOnly cookies) | mobile (tokens held in the device's secure storage)
    client: Mapped[str] = mapped_column(String(16), nullable=False, default="web")
    ip_address: Mapped[str | None] = mapped_column(String(64))


class PasswordResetToken(UUIDPrimaryKey, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
