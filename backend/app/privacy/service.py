"""Data protection (Ghana Data Protection Act, 2012 (Act 843)): export, erasure and retention.

* **Export**: an organisation can take a complete copy of its data (JSON in a zip).
* **Erasure**: an owner can ask for the organisation to be deleted. After a 30-day
  cooling-off period, everything the customer gave us or we collected for them is erased.
  The audit trail and payment records are kept (pseudonymised) because the law and tax
  rules require them.
* **Account deletion**: a person can delete their own account; it is anonymised in place so
  audit history stays intact without naming them.
* **Retention**: raw telemetry is kept only as long as the organisation chooses, within its
  plan.
"""

import hashlib
import io
import json
import logging
import secrets
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AuditLog,
    AuthSession,
    Base,
    CheckRun,
    DataExport,
    Feedback,
    Membership,
    Notification,
    Organisation,
    PushDevice,
    SecurityEvent,
    Subscription,
    User,
)
from app.security.passwords import hash_password
from app.security.rbac import Role
from app.services import storage

log = logging.getLogger("app.privacy")

DELETION_GRACE_DAYS = 30
EXPORT_TTL_DAYS = 7
NOTIFICATION_RETENTION_DAYS = 180
# Kept after erasure: the audit trail and billing records are legal records.
KEEP_ON_ERASURE = {"organisations", "audit_logs", "payments", "subscriptions", "feedback"}
# Never exported: secrets and hashes.
SECRET_COLUMNS = {
    "password_hash",
    "credential_hash",
    "token_hash",
    "token_encrypted",
    "secret_hash",
    "key_hash",
    "mfa_secret_encrypted",
    "mfa_pending_secret_encrypted",
    "mfa_recovery_code_hashes",
    "refresh_token_hash",
    "previous_token_hash",
    "storage_key",
}


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _rows(db: Session, table, org_id: uuid.UUID) -> list[dict]:
    cols = [c for c in table.columns if c.name not in SECRET_COLUMNS]
    result = db.execute(
        select(*cols).where(table.c.organisation_id == org_id).limit(200_000)
    ).mappings()
    return [{k: _jsonable(v) for k, v in row.items()} for row in result]


def build_export(db: Session, org: Organisation) -> tuple[bytes, dict[str, int]]:
    """Every organisation-scoped table, as JSON, plus the people who belong to it."""
    buf = io.BytesIO()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = {c.name: _jsonable(getattr(org, c.key)) for c in Organisation.__table__.columns}
        zf.writestr("organisation.json", json.dumps(profile, indent=2))
        people = db.execute(
            select(
                User.full_name,
                User.email,
                User.username,
                Membership.role,
                Membership.status,
                Membership.created_at,
                User.mfa_enabled,
            )
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organisation_id == org.id)
        ).mappings()
        members = [{k: _jsonable(v) for k, v in r.items()} for r in people]
        zf.writestr("members.json", json.dumps(members, indent=2))
        counts["members"] = len(members)
        for table in Base.metadata.sorted_tables:
            if "organisation_id" not in table.c or table.name in {"memberships", "data_exports"}:
                continue
            rows = _rows(db, table, org.id)
            counts[table.name] = len(rows)
            zf.writestr(f"{table.name}.json", json.dumps(rows, indent=2))
        zf.writestr(
            "README.txt",
            f"Data export for {org.name}\n"
            f"Created {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by {settings.brand_product_name}.\n\n"
            "Each .json file holds one kind of record. Secrets (password hashes, device "
            "credentials, keys) are never included. Evidence files and reports can be downloaded "
            "from the app while the organisation exists.\n",
        )
    return buf.getvalue(), counts


def create_export(db: Session, org: Organisation, user: User) -> DataExport:
    data, counts = build_export(db, org)
    key = storage.put(org.id, "exports", data)
    export = DataExport(
        organisation_id=org.id,
        requested_by=user.id,
        status="ready",
        storage_key=key,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        summary=", ".join(f"{n} {t.replace('_', ' ')}" for t, n in counts.items() if n),
        expires_at=datetime.now(UTC) + timedelta(days=EXPORT_TTL_DAYS),
    )
    db.add(export)
    db.flush()
    return export


# --- Erasure ----------------------------------------------------------------------------------


def _owner_engine():
    # Erasure needs the owner role: the application role is deliberately unable to delete the
    # append-only incident timeline.
    return create_engine(settings.migration_database_url, pool_pre_ping=True)


def erase_organisation(org_id: uuid.UUID) -> dict[str, int]:
    """Irreversibly erase one organisation's data. Keeps a pseudonymised shell row."""
    removed: dict[str, int] = {}
    engine = _owner_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            for table in reversed(Base.metadata.sorted_tables):
                if "organisation_id" not in table.c or table.name in KEEP_ON_ERASURE:
                    continue
                n = conn.execute(delete(table).where(table.c.organisation_id == org_id)).rowcount
                if n:
                    removed[table.name] = n
            conn.execute(
                update(Feedback.__table__)
                .where(Feedback.__table__.c.organisation_id == org_id)
                .values(organisation_id=None)
            )
            conn.execute(
                update(Subscription.__table__)
                .where(Subscription.__table__.c.organisation_id == org_id)
                .values(status="cancelled")
            )
            conn.execute(
                update(Organisation.__table__)
                .where(Organisation.__table__.c.id == org_id)
                .values(
                    name="Deleted organisation",
                    industry=None,
                    size=None,
                    phone=None,
                    address=None,
                    website=None,
                    status="deleted",
                    deleted_at=datetime.now(UTC),
                )
            )
    finally:
        engine.dispose()
    removed["stored_files"] = storage.delete_organisation(org_id)
    return removed


def run_due_erasures(db: Session, now: datetime | None = None) -> int:
    """Erase organisations whose cooling-off period has ended. Runs in the monitor worker."""
    now = now or datetime.now(UTC)
    due = db.scalars(
        select(Organisation.id).where(
            Organisation.deletion_scheduled_for.is_not(None),
            Organisation.deletion_scheduled_for <= now,
            Organisation.deleted_at.is_(None),
        )
    ).all()
    db.commit()
    for org_id in due:
        removed = erase_organisation(org_id)
        log.info("erased organisation %s: %s", org_id, removed)
        db.add(
            AuditLog(
                organisation_id=org_id,
                actor_label="system",
                action="organisation.erased",
                resource_type="organisation",
                resource_id=str(org_id),
                details=removed,
            )
        )
        db.commit()
    return len(due)


def anonymise_user(db: Session, user: User) -> None:
    """Delete a person's account in place: no name, email or credentials remain."""
    user.email = f"deleted-{user.id.hex}@deleted.invalid"
    user.username = None
    user.full_name = "Deleted user"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.mfa_enabled = False
    user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted = None
    user.mfa_recovery_code_hashes = []
    user.status = "deleted"
    db.execute(delete(Membership).where(Membership.user_id == user.id))
    db.execute(delete(PushDevice).where(PushDevice.user_id == user.id))
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason="account_deleted")
    )


def sole_owner_of(db: Session, user: User) -> list[str]:
    """Organisations that would be left without an owner if this person left."""
    names = []
    for _membership, org in db.execute(
        select(Membership, Organisation)
        .join(Organisation, Organisation.id == Membership.organisation_id)
        .where(
            Membership.user_id == user.id,
            Membership.role == Role.OWNER,
            Membership.status == "active",
            Organisation.deleted_at.is_(None),
        )
    ).all():
        owners = db.scalar(
            select(text("count(*)"))
            .select_from(Membership)
            .where(
                Membership.organisation_id == org.id,
                Membership.role == Role.OWNER,
                Membership.status == "active",
            )
        )
        if owners <= 1:
            names.append(org.name)
    return names


# --- Retention --------------------------------------------------------------------------------


def prune_telemetry(db: Session, now: datetime | None = None) -> int:
    """Delete raw telemetry older than each organisation's retention setting."""
    now = now or datetime.now(UTC)
    removed = 0
    for org_id, days in db.execute(
        select(Organisation.id, Organisation.telemetry_retention_days).where(
            Organisation.deleted_at.is_(None)
        )
    ).all():
        cutoff = now - timedelta(days=days)
        removed += (
            db.execute(
                delete(SecurityEvent).where(
                    SecurityEvent.organisation_id == org_id, SecurityEvent.received_at < cutoff
                )
            ).rowcount
            or 0
        )
        removed += (
            db.execute(
                delete(CheckRun).where(
                    CheckRun.organisation_id == org_id, CheckRun.completed_at < cutoff
                )
            ).rowcount
            or 0
        )
    removed += (
        db.execute(
            delete(Notification).where(
                Notification.created_at < now - timedelta(days=NOTIFICATION_RETENTION_DAYS)
            )
        ).rowcount
        or 0
    )
    expired = db.scalars(
        select(DataExport).where(DataExport.status == "ready", DataExport.expires_at < now)
    ).all()
    for export in expired:
        if export.storage_key:
            storage.delete(export.organisation_id, export.storage_key)
        export.status, export.storage_key = "expired", None
    db.commit()
    return removed
