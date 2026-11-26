import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.endpoints import health, wazuh
from app.main import app
from app.models import Agent, AgentEnrolmentToken, Asset, Finding, Subscription
from app.schemas.endpoint import Inventory
from app.services.email import read_dev_mailbox
from app.workers.monitor import check_offline_agents
from tests.conftest import create_org, invite_and_join, register

INVENTORY = {
    "hostname": "ACC-LT-07",
    "os_family": "windows",
    "os_name": "Windows 11 Pro",
    "os_version": "10.0.22631",
    "firewall_enabled": True,
    "antivirus_enabled": True,
    "disk_encrypted": True,
    "disk_used_percent": 40.0,
}


def device() -> TestClient:
    """A device: no cookies, no browser session."""
    return TestClient(app)


def new_token(api, **body) -> str:
    r = api.post("/api/v1/endpoints/enrolment-tokens", {"asset_type": "laptop", **body})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def enrol(token: str, machine_id: str = "machine-aaaa-0001", inventory=None):
    return device().post(
        "/api/v1/agent/enrol",
        json={
            "token": token,
            "machine_id": machine_id,
            "agent_version": "1.0.0",
            "inventory": inventory or INVENTORY,
        },
    )


def auth(credential: str) -> dict:
    return {"Authorization": f"Agent {credential}"}


def heartbeat(credential: str, inventory=None, **extra):
    return device().post(
        "/api/v1/agent/heartbeat",
        headers=auth(credential),
        json={"agent_version": "1.0.0", "inventory": inventory or INVENTORY, **extra},
    )


def send_events(credential: str, events: list[dict]):
    return device().post("/api/v1/agent/events", headers=auth(credential), json={"events": events})


def failure(i: int, account="admin", minutes_ago=0):
    return {
        "event_id": f"f-{i}-{uuid.uuid4().hex[:6]}",
        "event_type": "authentication.failure",
        "timestamp": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
        "data": {"account": account, "source_ip": "203.0.113.9"},
    }


@pytest.fixture
def enrolled(owner):
    r = enrol(new_token(owner))
    assert r.status_code == 200, r.text
    return r.json()["credential"]


def test_enrolment_creates_an_authorised_monitored_device(owner, enrolled):
    endpoints = owner.get("/api/v1/endpoints").json()
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep["hostname"] == "ACC-LT-07" and ep["online"] and ep["asset"]["type"] == "laptop"
    asset = owner.get(f"/api/v1/assets/{ep['asset']['id']}").json()
    assert asset["monitoring_status"] == "monitoring"
    assert asset["authorisation"]["method"] == "agent"
    assert heartbeat(enrolled).status_code == 200


def test_tokens_are_single_use_and_expire(owner):
    token = new_token(owner)
    assert enrol(token).status_code == 200
    assert enrol(token, machine_id="machine-bbbb-0002").status_code == 401

    # Spec scenario 3: an expired token is refused.
    expired = new_token(owner, max_uses=5)
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(AgentEnrolmentToken).values(expires_at=datetime.now(UTC) - timedelta(1)))
    db.commit()
    db.close()
    r = enrol(expired, machine_id="machine-cccc-0003")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_enrolment_token"


def test_revoked_tokens_are_refused(owner):
    token = new_token(owner, max_uses=10)
    token_id = owner.get("/api/v1/endpoints/enrolment-tokens").json()[0]["id"]
    owner.delete(f"/api/v1/endpoints/enrolment-tokens/{token_id}")
    assert enrol(token).status_code == 401


def test_forged_organisation_identifiers_are_rejected_or_ignored(owner, enrolled):
    """Spec scenario 2: the organisation always comes from the enrolled agent."""
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    r = heartbeat(enrolled, organisation_id=other.org_id)
    assert r.status_code == 422
    r = send_events(enrolled, [{**failure(1), "organisation_id": other.org_id}])
    assert r.status_code == 422
    # Data fields are just data: they can't move an event to another organisation.
    r = send_events(enrolled, [{**failure(2), "data": {"organisation_id": other.org_id}}])
    assert r.json()["accepted"] == 1
    assert other.get("/api/v1/endpoints/events").json()["total"] == 0
    assert owner.get("/api/v1/endpoints/events").json()["total"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "events": [
                {"event_id": "x", "event_type": "rm -rf", "timestamp": "2026-01-01T00:00:00Z"}
            ]
        },
        {"events": [failure(i) for i in range(501)]},
        {"events": [{**failure(1), "data": {"blob": "x" * 9000}}]},
        {"events": [{"event_type": "generic", "timestamp": "not-a-date"}]},
        {"events": []},
        {"something": "else"},
    ],
)
def test_malformed_telemetry_is_rejected(enrolled, payload):
    """Spec scenario 5: strict schema validation on everything a device sends."""
    r = device().post("/api/v1/agent/events", headers=auth(enrolled), json=payload)
    assert r.status_code == 422


def test_bad_credentials_and_revoked_agents(owner, enrolled):
    agent_id = enrolled.split(":")[0]
    assert heartbeat(f"{agent_id}:wrong-secret").status_code == 401
    assert heartbeat(f"{uuid.uuid4()}:whatever").status_code == 401
    assert device().post("/api/v1/agent/heartbeat", json={}).status_code == 401
    endpoint = owner.get("/api/v1/endpoints").json()[0]
    assert owner.post(f"/api/v1/endpoints/{endpoint['id']}/revoke").status_code == 200
    assert heartbeat(enrolled).status_code == 401
    # Re-enrolling the same machine with a fresh token brings it back on the same asset.
    r = enrol(new_token(owner))
    assert r.status_code == 200
    again = owner.get("/api/v1/endpoints").json()
    assert len(again) == 1 and again[0]["asset"]["id"] == endpoint["asset"]["id"]


def test_health_findings_open_and_clear(owner, enrolled):
    heartbeat(enrolled, {**INVENTORY, "firewall_enabled": False, "os_name": "Windows 10 Pro"})
    keys = {f["rule_key"] for f in owner.get("/api/v1/findings").json()["items"]}
    assert keys == {"firewall_disabled", "os_unsupported"}
    heartbeat(enrolled)
    assert owner.get("/api/v1/findings").json()["total"] == 0


def test_silent_devices_are_flagged_and_recover(owner, enrolled):
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(Agent).values(last_seen_at=datetime.now(UTC) - timedelta(minutes=20)))
    db.commit()
    db.close()
    check_offline_agents()
    findings = owner.get("/api/v1/findings").json()["items"]
    assert [f["rule_key"] for f in findings] == ["agent_offline"]
    ep = owner.get("/api/v1/endpoints").json()[0]
    assert ep["online"] is False
    assert (
        owner.get(f"/api/v1/assets/{ep['asset']['id']}").json()["monitoring_status"] == "degraded"
    )
    heartbeat(enrolled)
    assert owner.get("/api/v1/findings").json()["total"] == 0
    assert (
        owner.get(f"/api/v1/assets/{ep['asset']['id']}").json()["monitoring_status"] == "monitoring"
    )


def test_one_failed_login_is_not_an_attack(owner, enrolled):
    send_events(enrolled, [failure(1)])
    assert owner.get("/api/v1/findings").json()["total"] == 0


def test_brute_force_and_successful_login_after_it(owner, enrolled):
    r = send_events(enrolled, [failure(i) for i in range(12)])
    assert r.json() == {"accepted": 12, "duplicates": 0}
    findings = owner.get("/api/v1/findings").json()["items"]
    assert [f["rule_key"] for f in findings] == ["repeated_failed_logins"]
    assert findings[0]["evidence"]["failed_attempts"] == 12

    success = {
        "event_id": "ok-1",
        "event_type": "authentication.success",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"account": "ADMIN", "source_ip": "203.0.113.9"},
    }
    send_events(enrolled, [success])
    alerts = owner.get("/api/v1/alerts", params={"severity": "critical"}).json()["items"]
    assert [a["title"] for a in alerts] == ["Successful sign-in after repeated failures"]
    assert any(
        "Successful sign-in after repeated failures" in m["subject"] for m in read_dev_mailbox()
    )


def test_old_failures_outside_the_window_do_not_count(owner, enrolled):
    send_events(enrolled, [failure(i, minutes_ago=30) for i in range(9)] + [failure(99)])
    assert owner.get("/api/v1/findings").json()["total"] == 0


def test_malware_and_idempotent_events(owner, enrolled):
    event = {
        "event_id": "mw-1",
        "event_type": "malware.detected",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"threat": "Trojan:Win32/Agent", "path": "C:\\Users\\a\\x.exe"},
    }
    assert send_events(enrolled, [event]).json() == {"accepted": 1, "duplicates": 0}
    assert send_events(enrolled, [event]).json() == {"accepted": 0, "duplicates": 1}
    finding = owner.get("/api/v1/findings").json()["items"][0]
    assert finding["rule_key"] == "malware_detected" and finding["severity"] == "critical"
    assert finding["evidence"]["threat"] == "Trojan:Win32/Agent"
    events = owner.get("/api/v1/endpoints/events").json()
    assert events["total"] == 1 and events["items"][0]["severity"] == "critical"


def test_enrolment_respects_plan_limits(owner):
    for i in range(5):
        owner.post(
            "/api/v1/assets", {"name": f"PC{i}", "type": "workstation", "identifier": f"PC-{i}"}
        )
    r = enrol(new_token(owner))
    assert r.status_code == 402


def test_endpoint_data_is_isolated_and_permissioned(owner, enrolled):
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(Subscription).values(plan_code="business"))  # room for more members
    db.commit()
    db.close()
    send_events(enrolled, [failure(1)])
    ep = owner.get("/api/v1/endpoints").json()[0]
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get("/api/v1/endpoints").json() == []
    assert other.get("/api/v1/endpoints/events").json()["total"] == 0
    assert other.post(f"/api/v1/endpoints/{ep['id']}/revoke").status_code == 404

    analyst = invite_and_join(owner, "analyst@acme.example.com", "security_analyst")
    assert analyst.get("/api/v1/endpoints").status_code == 200
    assert analyst.post("/api/v1/endpoints/enrolment-tokens", {}).status_code == 403
    it = invite_and_join(owner, "it@acme.example.com", "it_admin")
    assert it.post("/api/v1/endpoints/enrolment-tokens", {}).status_code == 201
    employee = invite_and_join(owner, "staff@acme.example.com", "employee")
    assert employee.get("/api/v1/endpoints").status_code == 403


# --- Wazuh ---------------------------------------------------------------------------------

WAZUH_FAILED = {
    "timestamp": "2026-11-26T10:00:00.000+0000",
    "id": "1732615200.1001",
    "rule": {
        "level": 5,
        "description": "sshd: authentication failed.",
        "id": "5760",
        "groups": ["syslog", "sshd", "authentication_failed"],
    },
    "agent": {"id": "002", "name": "web-server-01", "ip": "10.0.0.12"},
    "data": {"srcip": "198.51.100.7", "dstuser": "root"},
}
WAZUH_DEFENDER = {
    "timestamp": "2026-11-26T10:05:00.000+0000",
    "id": "1732615500.2002",
    "rule": {
        "level": 12,
        "description": "Windows Defender: malware detected",
        "id": "62123",
        "groups": ["windows", "windows_defender"],
    },
    "agent": {"id": "003", "name": "RECEPTION-PC", "ip": "10.0.0.31"},
    "data": {"win": {"eventdata": {"threat Name": "Trojan:Win32/Wacatac"}}},
}
WAZUH_ADMIN = {
    "id": "a3",
    "rule": {
        "level": 8,
        "description": "Administrators group changed",
        "groups": ["windows", "group_changed"],
    },
    "agent": {"id": "003", "name": "RECEPTION-PC"},
    "data": {
        "win": {"eventdata": {"targetUserName": "Administrators", "subjectUserName": "temp-user"}}
    },
}


def test_wazuh_alert_mapping():
    assert wazuh.map_alert(WAZUH_FAILED)["event_type"] == "authentication.failure"
    assert wazuh.map_alert(WAZUH_FAILED)["data"]["account"] == "root"
    assert wazuh.map_alert(WAZUH_DEFENDER)["event_type"] == "malware.detected"
    assert wazuh.map_alert(WAZUH_ADMIN)["event_type"] == "account.privileged_created"
    noise = {**WAZUH_FAILED, "rule": {"level": 2, "groups": []}}
    assert wazuh.map_alert(noise) is None
    generic = wazuh.map_alert(
        {"id": "g", "rule": {"level": 13, "groups": ["custom"]}, "agent": {"id": "9"}}
    )
    assert generic["event_type"] == "generic" and generic["severity"] == "high"
    assert wazuh.map_alert(WAZUH_FAILED)["timestamp"].tzinfo is not None


def wazuh_post(key: str, payload: dict):
    return device().post(
        "/api/v1/integrations/wazuh/alerts",
        json=payload,
        headers={"Authorization": f"Bearer {key}"},
    )


def test_wazuh_connector_end_to_end(owner):
    r = owner.post("/api/v1/integrations/keys", {"name": "Office Wazuh"})
    assert r.status_code == 201
    key = r.json()["key"]
    assert wazuh_post("smecm_int_nope_bad", WAZUH_FAILED).status_code == 401
    r = wazuh_post(key, {"alerts": [WAZUH_FAILED, WAZUH_DEFENDER, WAZUH_ADMIN]})
    assert r.json() == {"accepted": 3, "duplicates": 0}
    assert wazuh_post(key, WAZUH_FAILED).json() == {"accepted": 0, "duplicates": 1}

    endpoints = {e["hostname"]: e for e in owner.get("/api/v1/endpoints").json()}
    assert set(endpoints) == {"web-server-01", "RECEPTION-PC"}
    assert endpoints["RECEPTION-PC"]["source"] == "wazuh"
    keys = {f["rule_key"] for f in owner.get("/api/v1/findings").json()["items"]}
    assert keys == {"malware_detected", "privileged_account_created"}

    key_id = owner.get("/api/v1/integrations/keys").json()[0]["id"]
    owner.delete(f"/api/v1/integrations/keys/{key_id}")
    assert wazuh_post(key, WAZUH_FAILED).status_code == 401


def test_wazuh_keys_are_organisation_scoped(owner):
    key = owner.post("/api/v1/integrations/keys", {"name": "Wazuh"}).json()["key"]
    wazuh_post(key, WAZUH_DEFENDER)
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get("/api/v1/endpoints").json() == []
    analyst = invite_and_join(owner, "a@acme.example.com", "security_analyst")
    assert analyst.post("/api/v1/integrations/keys", {"name": "x"}).status_code == 403


# --- Pure rules ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "name", "version", "expected"),
    [
        ("windows", "Windows 10 Pro", "10.0.19045", True),
        ("windows", "Windows 11 Pro", "10.0.22631", False),
        ("windows", "Windows Server 2012 R2", "6.3", True),
        ("windows", "Windows Server 2022", "10.0.20348", False),
        ("macos", "macOS", "12.7.6", True),
        ("macos", "macOS", "27.2", False),
        ("linux", "Ubuntu", "20.04", True),
        ("linux", "Ubuntu", "24.04", False),
        ("linux", "Debian GNU/Linux", "12", False),
    ],
)
def test_unsupported_operating_systems(family, name, version, expected):
    assert health.unsupported_os(family, name, version) is expected


def test_unknown_values_never_create_findings():
    out = health.evaluate_inventory({"hostname": "x", "os_family": "linux"}, "server")
    assert out.status == "ok" and out.issues == []
    laptop = health.evaluate_inventory({**INVENTORY, "disk_encrypted": False}, "laptop")
    server = health.evaluate_inventory({**INVENTORY, "disk_encrypted": False}, "server")
    assert [i.rule_key for i in laptop.issues] == ["disk_not_encrypted"]
    assert server.issues == []


def test_reference_agent_inventory_matches_the_api_schema():
    path = Path(settings.agent_dist_path)
    if not path.is_file():
        pytest.skip("agent not mounted")
    out = subprocess.run(
        [sys.executable, str(path), "inventory"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    Inventory.model_validate(json.loads(out.stdout))


def test_asset_and_agent_rows_belong_to_the_token_organisation(owner, enrolled):
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    agent = db.scalar(select(Agent))
    asset = db.get(Asset, agent.asset_id)
    assert str(agent.organisation_id) == owner.org_id == str(asset.organisation_id)
    assert db.scalar(select(Finding)) is None
    db.close()
