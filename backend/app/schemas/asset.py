import re
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.asset import ASSET_TYPES, CRITICALITY_LEVELS
from app.schemas.common import ORMModel

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

AssetType = Literal[ASSET_TYPES]  # type: ignore[valid-type]
Criticality = Literal[CRITICALITY_LEVELS]  # type: ignore[valid-type]


def normalise_hostname(raw: str) -> str:
    host = raw.strip().rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Enter a valid domain name, such as example.com.gh.") from exc
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or not all(_LABEL.match(lbl) for lbl in labels):
        raise ValueError("Enter a valid domain name, such as example.com.gh.")
    if labels[-1].isdigit():
        raise ValueError("Enter a domain name, not an IP address.")
    return host


def normalise_identifier(asset_type: str, raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("Enter an identifier for this asset.")
    if asset_type == "domain":
        if "://" in value or "/" in value:
            raise ValueError("Enter just the domain name, such as example.com.gh.")
        return normalise_hostname(value)
    if asset_type == "website":
        if "://" not in value:
            value = "https://" + value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"}:
            raise ValueError("Website addresses must start with https:// or http://.")
        if parts.username or parts.password:
            raise ValueError("Do not include a username or password in the address.")
        host = normalise_hostname(parts.hostname or "")
        port = f":{parts.port}" if parts.port and parts.port not in {80, 443} else ""
        return f"https://{host}{port}"
    if len(value) > 500:
        raise ValueError("The identifier is too long.")
    return value


class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    criticality: Criticality = "medium"
    department_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    technology: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter a name.")
        return v

    @field_validator("technology", "location", "notes")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class AssetCreate(AssetBase):
    type: AssetType
    identifier: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _normalise(self) -> "AssetCreate":
        self.identifier = normalise_identifier(self.type, self.identifier)
        return self


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    identifier: str | None = Field(default=None, min_length=1, max_length=500)
    criticality: Criticality | None = None
    department_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    technology: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class AuthorisationOut(ORMModel):
    id: uuid.UUID
    method: str
    challenge: str
    status: str
    failure_reason: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    verified_at: datetime | None
    evidence: dict


class VerificationInstructions(BaseModel):
    method: str
    summary: str
    steps: list[str]
    record_name: str | None = None
    record_value: str | None = None
    file_url: str | None = None
    file_contents: str | None = None


class AssetOut(ORMModel):
    id: uuid.UUID
    name: str
    identifier: str
    type: str
    category: str = ""
    criticality: str
    status: str
    monitoring_status: str
    risk_level: str
    technology: str | None
    location: str | None
    notes: str | None
    department_id: uuid.UUID | None
    department_name: str | None = None
    owner_user_id: uuid.UUID | None
    owner_name: str | None = None
    last_seen_at: datetime | None
    last_successful_check_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetDetail(AssetOut):
    authorisation: AuthorisationOut | None = None
    instructions: VerificationInstructions | None = None
    verification_methods: list[str]


class VerificationStart(BaseModel):
    method: Literal["dns_txt", "http_file", "attestation"]
    statement: str | None = Field(default=None, max_length=1000)


class AuditEntryOut(ORMModel):
    id: uuid.UUID
    action: str
    actor_label: str | None
    resource_type: str | None
    resource_id: str | None
    details: dict
    ip_address: str | None
    created_at: datetime
