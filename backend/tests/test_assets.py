import socket

import pytest

from app.api.v1 import assets as assets_api
from app.services import verification
from app.services.verification import CheckResult, UnsafeTarget


def test_create_normalises_website_and_rejects_duplicates(owner):
    r = owner.post(
        "/api/v1/assets",
        {"name": "Shop", "type": "website", "identifier": "Shop.Example.com.gh/path"},
    )
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["identifier"] == "https://shop.example.com.gh"
    assert asset["monitoring_status"] == "not_monitored"
    assert asset["verification_methods"] == ["dns_txt", "http_file"]
    r = owner.post(
        "/api/v1/assets",
        {"name": "Dup", "type": "website", "identifier": "https://shop.example.com.gh"},
    )
    assert r.status_code == 409


def test_invalid_domain_is_rejected(owner):
    r = owner.post(
        "/api/v1/assets", {"name": "Bad", "type": "domain", "identifier": "not a domain"}
    )
    assert r.status_code == 422


def test_plan_asset_limit(owner):
    for i in range(5):
        assert (
            owner.post(
                "/api/v1/assets",
                {"name": f"PC {i}", "type": "workstation", "identifier": f"PC-{i}"},
            ).status_code
            == 201
        )
    r = owner.post("/api/v1/assets", {"name": "PC 6", "type": "workstation", "identifier": "PC-6"})
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "plan_limit_reached"


def test_internal_asset_authorised_by_attestation(owner):
    asset = owner.post(
        "/api/v1/assets", {"name": "Server", "type": "server", "identifier": "srv1"}
    ).json()
    url = f"/api/v1/assets/{asset['id']}/verification"
    assert owner.post(url, {"method": "dns_txt"}).status_code == 422
    assert owner.post(url, {"method": "attestation"}).status_code == 422  # statement required
    r = owner.post(url, {"method": "attestation", "statement": "We own this server."})
    assert r.status_code == 200
    assert r.json()["monitoring_status"] == "authorised"
    assert r.json()["authorisation"]["status"] == "verified"


def test_website_cannot_be_self_attested_and_needs_technical_proof(owner, monkeypatch):
    asset = owner.post(
        "/api/v1/assets", {"name": "Site", "type": "website", "identifier": "example.com.gh"}
    ).json()
    base = f"/api/v1/assets/{asset['id']}"
    r = owner.post(f"{base}/verification", {"method": "attestation", "statement": "trust me"})
    assert r.status_code == 422

    r = owner.post(f"{base}/verification", {"method": "dns_txt"})
    detail = r.json()
    assert detail["instructions"]["record_name"] == "_smecm-challenge.example.com.gh"
    assert detail["instructions"]["record_value"].startswith("smecm-verification=")

    monkeypatch.setattr(
        verification, "check_dns_txt", lambda host, ch: CheckResult(False, "No TXT record", {})
    )
    r = owner.post(f"{base}/verify")
    assert r.json()["monitoring_status"] == "not_monitored"
    assert r.json()["authorisation"]["status"] == "failed"

    monkeypatch.setattr(
        verification, "check_dns_txt", lambda host, ch: CheckResult(True, "matched", {})
    )
    r = owner.post(f"{base}/verify")
    assert r.json()["monitoring_status"] == "authorised"

    # Changing the address invalidates the proof.
    r = owner.patch(base, {"identifier": "other.example.com.gh"})
    assert r.json()["monitoring_status"] == "not_monitored"
    assert r.json()["authorisation"] is None


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fd00::1",
        "::ffff:169.254.169.254",
        "100.64.0.1",
    ],
)
def test_verification_refuses_internal_addresses(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(family, socket.SOCK_STREAM, 6, "", (address, 443))],
    )
    with pytest.raises(UnsafeTarget):
        verification.resolve_public_addresses("innocent-looking.example.com")
    result = verification.check_http_file("innocent-looking.example.com", "abc")
    assert result.ok is False


def test_archive_and_restore(owner):
    asset = owner.post(
        "/api/v1/assets", {"name": "Old PC", "type": "workstation", "identifier": "OLD-1"}
    ).json()
    owner.post(f"/api/v1/assets/{asset['id']}/archive")
    assert owner.get("/api/v1/assets").json()["total"] == 0
    assert owner.get("/api/v1/assets?status=archived").json()["total"] == 1
    owner.post(f"/api/v1/assets/{asset['id']}/restore")
    assert owner.get("/api/v1/assets").json()["total"] == 1


def test_list_filters_and_activity(owner):
    owner.post("/api/v1/assets", {"name": "Site", "type": "website", "identifier": "a.com.gh"})
    srv = owner.post(
        "/api/v1/assets",
        {"name": "Server", "type": "server", "identifier": "s1", "criticality": "critical"},
    ).json()
    assert owner.get("/api/v1/assets?category=servers").json()["total"] == 1
    assert owner.get("/api/v1/assets?criticality=critical").json()["total"] == 1
    assert owner.get("/api/v1/assets?q=site").json()["total"] == 1
    owner.patch(f"/api/v1/assets/{srv['id']}", {"name": "Main server"})
    activity = owner.get(f"/api/v1/assets/{srv['id']}/activity").json()["items"]
    assert [e["action"] for e in activity] == ["asset.updated", "asset.created"]


def test_overview_never_invents_a_score(owner):
    data = owner.get("/api/v1/overview").json()
    assert data["posture_score"] is None
    assert {r["id"] for r in data["recommendations"]} >= {"self_mfa", "first_asset"}


def test_assets_module_has_no_hard_delete():
    assert not any("DELETE" in getattr(r, "methods", set()) for r in assets_api.router.routes)
