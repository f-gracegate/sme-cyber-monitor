"""Tenant isolation and authorisation: the scenarios the release rule depends on."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from app.core.db import SessionLocal, set_tenant_context
from app.models import Asset, AuditLog
from tests.conftest import create_org, invite_and_join, register

SERVER = {"name": "File server", "type": "server", "identifier": "fs01"}


@pytest.fixture
def two_tenants():
    a = register("a@alpha.example.com")
    create_org(a, "Alpha Ltd")
    b = register("b@beta.example.com")
    create_org(b, "Beta Ltd")
    asset_b = b.post("/api/v1/assets", SERVER).json()
    return a, b, asset_b


def test_user_cannot_read_another_organisations_asset(two_tenants):
    a, b, asset_b = two_tenants
    # Using their own organisation header: the asset simply does not exist for them.
    assert a.get(f"/api/v1/assets/{asset_b['id']}").status_code == 404
    assert a.patch(f"/api/v1/assets/{asset_b['id']}", {"name": "pwned"}).status_code == 404
    # Claiming the other organisation's ID in the header is refused outright.
    r = a.get(f"/api/v1/assets/{asset_b['id']}", headers={"x-organisation-id": b.org_id})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "organisation_not_found"
    assert a.get(f"/api/v1/organisations/{b.org_id}/members").status_code == 404
    assert a.get("/api/v1/assets").json()["total"] == 0


def test_cannot_link_another_organisations_records(two_tenants):
    a, b, _ = two_tenants
    dept_b = b.post(f"/api/v1/organisations/{b.org_id}/departments", {"name": "IT"}).json()
    r = a.post("/api/v1/assets", {**SERVER, "department_id": dept_b["id"]})
    assert r.status_code == 422


def test_row_level_security_blocks_cross_tenant_rows_in_the_database(two_tenants):
    a, b, _ = two_tenants
    a.post("/api/v1/assets", SERVER)
    db = SessionLocal()
    db.info["rls"] = {}
    # No tenant context at all: nothing is visible.
    assert db.scalars(select(Asset)).all() == []
    db.rollback()
    # Alpha's context: an unfiltered query still returns only Alpha's rows.
    set_tenant_context(db, org=a.org_id)
    rows = db.scalars(select(Asset)).all()
    assert {str(r.organisation_id) for r in rows} == {a.org_id}
    db.close()


def test_audit_log_is_append_only_for_the_application(owner):
    owner.post("/api/v1/assets", SERVER)
    db = SessionLocal()
    db.info["rls"] = {}
    set_tenant_context(db, org=owner.org_id)
    assert db.scalars(select(AuditLog)).first() is not None
    with pytest.raises(ProgrammingError):
        db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    db.rollback()
    set_tenant_context(db, org=owner.org_id)
    with pytest.raises(ProgrammingError):
        db.execute(text("DELETE FROM audit_logs"))
    db.close()


def test_removed_member_loses_access_immediately(owner):
    member = invite_and_join(owner, "tech@acme.example.com", "it_admin")
    assert member.get("/api/v1/assets").status_code == 200
    members = owner.get(f"/api/v1/organisations/{owner.org_id}/members").json()
    tech = next(m for m in members if m["email"] == "tech@acme.example.com")
    assert (
        owner.delete(f"/api/v1/organisations/{owner.org_id}/members/{tech['id']}").status_code
        == 204
    )
    assert member.get("/api/v1/assets").status_code == 404


def test_suspended_member_loses_access(owner):
    member = invite_and_join(owner, "temp@acme.example.com", "security_analyst")
    mid = next(
        m["id"]
        for m in owner.get(f"/api/v1/organisations/{owner.org_id}/members").json()
        if m["email"] == "temp@acme.example.com"
    )
    owner.patch(f"/api/v1/organisations/{owner.org_id}/members/{mid}", {"status": "suspended"})
    assert member.get("/api/v1/assets").status_code == 404


def test_privilege_escalation_is_refused(owner):
    admin = invite_and_join(owner, "admin@acme.example.com", "admin")
    members = admin.get(f"/api/v1/organisations/{owner.org_id}/members").json()
    me = next(m for m in members if m["is_you"])
    the_owner = next(m for m in members if m["role"] == "owner")
    base = f"/api/v1/organisations/{owner.org_id}/members"
    assert admin.patch(f"{base}/{me['id']}", {"role": "owner"}).status_code == 409
    assert admin.patch(f"{base}/{the_owner['id']}", {"role": "employee"}).status_code == 403
    assert admin.delete(f"{base}/{the_owner['id']}").status_code == 403
    r = admin.post(
        f"/api/v1/organisations/{owner.org_id}/invitations",
        {"email": "boss@acme.example.com", "role": "owner"},
    )
    assert r.status_code == 403


def test_last_owner_cannot_be_removed_or_demoted(owner):
    second = invite_and_join(owner, "co@acme.example.com", "owner")
    members = second.get(f"/api/v1/organisations/{owner.org_id}/members").json()
    first = next(m for m in members if m["email"] == "owner@acme.example.com")
    base = f"/api/v1/organisations/{owner.org_id}/members"
    assert second.patch(f"{base}/{first['id']}", {"role": "admin"}).status_code == 200
    me = next(m for m in members if m["is_you"])
    owner_now_admin = owner
    assert owner_now_admin.patch(f"{base}/{me['id']}", {"role": "admin"}).status_code == 403


@pytest.mark.parametrize(
    ("role", "can_write_assets", "can_read_audit", "can_manage_members"),
    [
        ("admin", True, True, True),
        ("it_admin", True, False, False),
        ("security_analyst", False, False, False),
        ("auditor", False, True, False),
        ("executive", False, False, False),
        ("employee", False, False, False),
    ],
)
def test_role_permissions_are_enforced_by_the_api(
    owner, role, can_write_assets, can_read_audit, can_manage_members
):
    member = invite_and_join(owner, f"{role}@acme.example.com", role)
    r = member.post("/api/v1/assets", SERVER)
    assert (r.status_code == 201) is can_write_assets, r.text
    assert (member.get("/api/v1/audit-logs").status_code == 200) is can_read_audit
    r = member.post(
        f"/api/v1/organisations/{owner.org_id}/invitations",
        {"email": "x@acme.example.com", "role": "employee"},
    )
    assert (r.status_code == 201) is can_manage_members


def test_invitation_only_works_for_the_invited_email(owner):
    r = owner.post(
        f"/api/v1/organisations/{owner.org_id}/invitations",
        {"email": "right@acme.example.com", "role": "employee"},
    )
    token = r.json()["invite_url"].rsplit("/", 1)[1]
    wrong = register("wrong@elsewhere.example.com")
    r = wrong.post("/api/v1/auth/invitations/accept", {"token": token})
    assert r.status_code == 403
    assert wrong.get("/api/v1/organisations").json() == []


def test_organisation_mfa_requirement(owner):
    from tests.conftest import enable_mfa

    member = invite_and_join(owner, "nomfa@acme.example.com", "it_admin")
    # The owner must use MFA before requiring it for everyone.
    r = owner.patch(f"/api/v1/organisations/{owner.org_id}", {"require_mfa": True})
    assert r.status_code == 409
    enable_mfa(owner)
    assert (
        owner.patch(f"/api/v1/organisations/{owner.org_id}", {"require_mfa": True}).status_code
        == 200
    )
    r = member.get("/api/v1/assets")
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_enrolment_required"
    enable_mfa(member)
    assert member.get("/api/v1/assets").status_code == 200


def test_platform_console_requires_platform_admin(owner):
    assert owner.get("/api/v1/platform/organisations").status_code == 403
