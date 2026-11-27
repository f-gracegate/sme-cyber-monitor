"""Operational commands.

python -m app.cli seed          create the platform administrator (idempotent)
python -m app.cli seed --demo   also create a demo organisation with sample assets
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.db import SessionLocal, system_context
from app.models import (
    Asset,
    AssetAuthorisation,
    Department,
    Membership,
    Organisation,
    Subscription,
    User,
)
from app.monitoring.engine import ensure_default_checks
from app.security.passwords import hash_password, password_policy_errors
from app.security.rbac import Role
from app.services import audit

DEMO_ORG_NAME = "Demo Business Ltd"
DEMO_ASSETS = [
    ("Company website", "https://example.com", "website", "high", "WordPress"),
    ("Primary domain", "example.com", "domain", "high", None),
    ("Front desk PC", "FRONTDESK-01", "workstation", "medium", "Windows 11 Pro"),
    ("Accounts laptop", "ACC-LT-02", "laptop", "high", "macOS 15"),
    ("File server", "fs01.office.local", "server", "critical", "Ubuntu 24.04 LTS"),
    ("Office firewall", "192.168.1.1", "firewall", "critical", "MikroTik RouterOS"),
]


def _authorise_demo(db, asset: Asset, admin: User) -> None:
    """Development only: example.com is reserved by IANA for documentation, so it's a safe,
    real target that lets the demo show live monitoring without a DNS change."""
    db.add(
        AssetAuthorisation(
            organisation_id=asset.organisation_id,
            asset_id=asset.id,
            method="dns_txt",
            challenge="development-demo",
            status="verified",
            evidence={"note": "Development demo seed. example.com is an IANA reserved domain."},
            requested_by=admin.id,
            verified_by=admin.id,
            verified_at=datetime.now(UTC),
        )
    )
    asset.monitoring_status = "authorised"
    ensure_default_checks(db, asset)


def seed(demo: bool) -> None:
    password = settings.seed_admin_password
    if not password:
        print("SEED_ADMIN_PASSWORD is not set; skipping administrator seed.")
        return
    if not settings.is_development and password_policy_errors(password):
        sys.exit("Refusing to seed: SEED_ADMIN_PASSWORD is too weak for this environment.")

    db = SessionLocal()
    db.info["rls"] = {}
    with system_context(db):
        admin = db.scalar(
            select(User).where(
                or_(
                    func.lower(User.username) == settings.seed_admin_username.lower(),
                    User.email == settings.seed_admin_email.lower(),
                )
            )
        )
        if admin is None:
            admin = User(
                email=settings.seed_admin_email.lower(),
                username=settings.seed_admin_username,
                full_name="Platform Administrator",
                password_hash=hash_password(password),
                is_platform_admin=True,
                must_change_password=True,
                password_changed_at=datetime.now(UTC),
                email_verified_at=datetime.now(UTC),
            )
            db.add(admin)
            db.flush()
            audit.record(
                db,
                "user.seeded",
                actor=admin,
                resource_type="user",
                resource_id=admin.id,
                actor_label="system",
            )
            print(f"Created administrator '{admin.username}' (password change required).")
        else:
            print(f"Administrator '{admin.username}' already exists; left unchanged.")

        if demo:
            org = db.scalar(
                select(Organisation)
                .join(Membership, Membership.organisation_id == Organisation.id)
                .where(Organisation.name == DEMO_ORG_NAME, Membership.user_id == admin.id)
            )
            if org is None:
                org = Organisation(
                    name=DEMO_ORG_NAME,
                    industry="retail",
                    size="11-50",
                    phone="+233 30 000 0000",
                    address="Accra, Ghana",
                    created_by=admin.id,
                )
                db.add(org)
                db.flush()
                db.add(Membership(organisation_id=org.id, user_id=admin.id, role=Role.OWNER))
                db.add(
                    Subscription(
                        organisation_id=org.id,
                        plan_code="professional",
                        status="trialing",
                        current_period_end=datetime.now(UTC) + timedelta(days=30),
                    )
                )
                depts = {}
                for name in ("Operations", "Finance", "IT"):
                    depts[name] = Department(organisation_id=org.id, name=name)
                    db.add(depts[name])
                db.flush()
                for name, ident, typ, crit, tech in DEMO_ASSETS:
                    dept = (
                        depts["IT"]
                        if typ in {"server", "firewall", "website", "domain"}
                        else depts["Finance"]
                        if typ == "laptop"
                        else depts["Operations"]
                    )
                    asset = Asset(
                        organisation_id=org.id,
                        name=name,
                        identifier=ident,
                        type=typ,
                        criticality=crit,
                        technology=tech,
                        department_id=dept.id,
                        owner_user_id=admin.id,
                        created_by=admin.id,
                    )
                    db.add(asset)
                    db.flush()
                    if typ in {"website", "domain"} and settings.is_development:
                        _authorise_demo(db, asset, admin)
                audit.record(
                    db,
                    "organisation.created",
                    actor=admin,
                    organisation_id=org.id,
                    resource_type="organisation",
                    resource_id=org.id,
                    details={"name": org.name, "seeded": True},
                )
                print(f"Created demo organisation '{DEMO_ORG_NAME}'.")
        db.commit()
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    seed_cmd = sub.add_parser("seed")
    seed_cmd.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.demo)


if __name__ == "__main__":
    main()
