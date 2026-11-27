import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel
from app.security.rbac import Role

INDUSTRIES = (
    "retail",
    "ecommerce",
    "hospitality",
    "education",
    "healthcare",
    "professional_services",
    "finance",
    "technology",
    "manufacturing",
    "logistics",
    "ngo",
    "other",
)
SIZES = ("1-10", "11-50", "51-200", "201-500", "500+")


def _check_industry(v: str | None) -> str | None:
    if v is not None and v not in INDUSTRIES:
        raise ValueError("Choose an industry from the list.")
    return v


def _check_size(v: str | None) -> str | None:
    if v is not None and v not in SIZES:
        raise ValueError("Choose a company size from the list.")
    return v


def _strip_or_none(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class OrganisationFields(BaseModel):
    industry: str | None = None
    size: str | None = None
    country: str = Field(default="GH", min_length=2, max_length=2)
    timezone: str = Field(default="Africa/Accra", max_length=64)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=400)
    website: str | None = Field(default=None, max_length=300)

    @field_validator("industry")
    @classmethod
    def _industry(cls, v: str | None) -> str | None:
        return _check_industry(v)

    @field_validator("size")
    @classmethod
    def _size(cls, v: str | None) -> str | None:
        return _check_size(v)

    @field_validator("phone", "address", "website")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _strip_or_none(v)

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        return v.upper()


class OrganisationCreate(OrganisationFields):
    name: str = Field(min_length=2, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class OrganisationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    industry: str | None = None
    size: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=400)
    website: str | None = Field(default=None, max_length=300)
    require_mfa: bool | None = None

    @field_validator("industry")
    @classmethod
    def _industry(cls, v: str | None) -> str | None:
        return _check_industry(v)

    @field_validator("size")
    @classmethod
    def _size(cls, v: str | None) -> str | None:
        return _check_size(v)

    @field_validator("phone", "address", "website")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _strip_or_none(v)


class OrganisationOut(ORMModel):
    id: uuid.UUID
    name: str
    industry: str | None
    size: str | None
    country: str
    timezone: str
    phone: str | None
    address: str | None
    website: str | None
    status: str
    require_mfa: bool
    telemetry_retention_days: int = 30
    deletion_scheduled_for: datetime | None = None
    created_at: datetime


class OrganisationWithRole(OrganisationOut):
    role: str
    role_label: str


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    role_label: str
    status: str
    department_id: uuid.UUID | None
    department_name: str | None
    mfa_enabled: bool
    last_login_at: datetime | None
    joined_at: datetime
    is_you: bool


class MemberUpdate(BaseModel):
    role: Role | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    department_id: uuid.UUID | None = None
    clear_department: bool = False


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role


class InvitationOut(ORMModel):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    invited_by_email: str | None = None


class InvitationCreated(BaseModel):
    invitation: InvitationOut
    invite_url: str


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter a department name.")
        return v


class DepartmentOut(ORMModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class RoleOut(BaseModel):
    value: str
    label: str
    permissions: list[str]
