import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=64)
    invitation_token: str | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter your full name.")
        return v

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Usernames are 3–64 characters: letters, numbers, dots, dashes or underscores."
            )
        return v


Client = Literal["web", "mobile"]


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320, description="Email or username")
    password: str = Field(min_length=1, max_length=256)
    # "mobile" returns tokens in the response body for the app's secure storage instead of
    # setting browser cookies.
    client: Client = "web"


class MFAVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=1, max_length=2000)
    code: str = Field(min_length=6, max_length=32)
    client: Client = "web"


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - a token type name, not a secret
    expires_in: int


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class MFACodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MFADisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=32)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class MembershipSummary(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    role: str
    role_label: str
    permissions: list[str]
    require_mfa: bool


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    username: str | None
    full_name: str
    is_platform_admin: bool
    must_change_password: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipSummary]


class LoginResponse(BaseModel):
    status: Literal["ok", "mfa_required"]
    mfa_token: str | None = None
    me: MeResponse | None = None
    tokens: TokenPair | None = None


class RefreshResponse(BaseModel):
    message: str
    tokens: TokenPair | None = None


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MFAEnableResponse(BaseModel):
    recovery_codes: list[str]


class InvitationPreview(BaseModel):
    organisation_name: str
    email: str
    role: str
    role_label: str
    status: Literal["pending", "expired", "accepted", "revoked"]
    account_exists: bool
