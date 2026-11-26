import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import SessionLocal
from app.main import app
from app.models import Subscription
from tests.conftest import create_org, register
from tests.test_endpoints import INVENTORY

HEALTH = {
    "hostname": "collector-hq",
    "uptime_seconds": 60,
    "queue_depth": 0,
    "events_dropped": 0,
    "events_forwarded": 0,
    "capabilities": ["syslog_udp", "probe"],
    "sources": [
        {
            "name": "syslog:192.168.1.1",
            "type": "syslog",
            "events": 3,
            "last_event_at": "2026-11-26T10:00:00+00:00",
        }
    ],
    "listen": {"syslog_udp": 5514},
}


def device() -> TestClient:
    return TestClient(app)


def set_plan(code: str) -> None:
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(update(Subscription).values(plan_code=code))
    db.commit()
    db.close()


def token(api, kind="collector") -> str:
    r = api.post("/api/v1/endpoints/enrolment-tokens", {"kind": kind})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def enrol(tok: str, machine="collector-machine-01"):
    return device().post(
        "/api/v1/collector/enrol",
        json={
            "token": tok,
            "machine_id": machine,
            "version": "1.0.0",
            "name": "HQ",
            "health": HEALTH,
        },
    )


def hb(cred: str, probes=None, **health):
    return device().post(
        "/api/v1/collector/heartbeat",
        headers={"Authorization": f"Agent {cred}"},
        json={"version": "1.0.0", "health": {**HEALTH, **health}, "probes": probes or []},
    )


def events(cred: str, items: list[dict]):
    return device().post(
        "/api/v1/collector/events",
        headers={"Authorization": f"Agent {cred}"},
        json={"events": items},
    )


def ev(event_type: str, device_hint=None, count=1, **data):
    return {
        "event_id": uuid.uuid4().hex,
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "device": device_hint,
        "count": count,
        "data": data,
    }


def authorised_device(api, name, identifier, asset_type="firewall") -> str:
    asset = api.post(
        "/api/v1/assets", {"name": name, "type": asset_type, "identifier": identifier}
    ).json()
    api.post(
        f"/api/v1/assets/{asset['id']}/verification",
        {"method": "attestation", "statement": "Our office firewall."},
    )
    return asset["id"]


@pytest.fixture
def collector(owner):
    set_plan("professional")
    r = enrol(token(owner))
    assert r.status_code == 200, r.text
    return r.json()["credential"]


def rules(api) -> set[str]:
    return {f["rule_key"] for f in api.get("/api/v1/findings").json()["items"]}


def test_collectors_need_a_plan_that_includes_them(owner):
    r = owner.post("/api/v1/endpoints/enrolment-tokens", {"kind": "collector"})
    assert r.status_code == 402
    set_plan("professional")
    assert enrol(token(owner)).status_code == 200
    assert enrol(token(owner), machine="collector-machine-02").status_code == 200
    assert (
        owner.post("/api/v1/endpoints/enrolment-tokens", {"kind": "collector"}).status_code == 402
    )  # allowance of 2 used


def test_token_and_credential_kinds_cannot_be_mixed(owner, collector):
    agent_token = token(owner, "agent")
    assert enrol(agent_token, machine="x-collector-9").status_code == 401
    collector_token = token(owner)
    r = device().post(
        "/api/v1/agent/enrol",
        json={
            "token": collector_token,
            "machine_id": "machine-zzzz",
            "agent_version": "1",
            "inventory": INVENTORY,
        },
    )
    assert r.status_code == 401
    r = device().post(
        "/api/v1/agent/heartbeat",
        headers={"Authorization": f"Agent {collector}"},
        json={"agent_version": "1", "inventory": INVENTORY},
    )
    assert r.status_code == 401


def test_probe_targets_are_only_this_organisations_authorised_devices(owner, collector):
    fw = authorised_device(owner, "Office firewall", "192.168.1.1")
    owner.post(
        "/api/v1/assets",
        {"name": "Unverified switch", "type": "switch", "identifier": "192.168.1.2"},
    )
    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    other_fw = authorised_device(other, "Their firewall", "10.9.9.9")

    targets = hb(collector).json()["probe_targets"]
    assert [t["asset_id"] for t in targets] == [fw]

    # A forged result for another organisation's device is ignored.
    hb(collector, [{"asset_id": other_fw, "reachable": False}] * 1)
    assert other.get("/api/v1/findings").json()["total"] == 0


def test_unreachable_devices_raise_and_clear(owner, collector):
    fw = authorised_device(owner, "Office firewall", "192.168.1.1")
    for _ in range(2):
        hb(collector, [{"asset_id": fw, "reachable": False}])
    assert "network_device_unreachable" not in rules(owner)  # needs three in a row
    hb(collector, [{"asset_id": fw, "reachable": False}])
    assert "network_device_unreachable" in rules(owner)
    devices = owner.get("/api/v1/network/devices").json()
    assert devices[0]["availability"] == "unreachable"
    hb(collector, [{"asset_id": fw, "reachable": True, "latency_ms": 3.2, "method": "tcp/443"}])
    assert "network_device_unreachable" not in rules(owner)
    devices = owner.get("/api/v1/network/devices").json()
    assert devices[0]["availability"] == "reachable" and devices[0]["latency_ms"] == 3.2


def test_heartbeat_with_traffic_and_source_stats(owner, collector):
    r = device().post(
        "/api/v1/collector/heartbeat",
        headers={"Authorization": f"Agent {collector}"},
        json={
            "version": "1.0.0",
            "health": HEALTH,
            "traffic": {
                "window_seconds": 60,
                "connections": 10,
                "bytes_in": 5000,
                "bytes_out": 700,
                "top_talkers": [{"host": "192.168.1.5", "bytes": 5700}],
            },
        },
    )
    assert r.status_code == 200, r.text
    c = owner.get("/api/v1/network/collectors").json()[0]
    assert c["sources"][0]["events"] == 3 and c["traffic"]["connections"] == 10


def test_collector_backlog_is_reported(owner, collector):
    hb(collector, events_dropped=120)
    assert "collector_dropping_events" in rules(owner)
    hb(collector)
    assert "collector_dropping_events" not in rules(owner)


def test_config_change_lands_on_the_matching_device(owner, collector):
    fw = authorised_device(owner, "FW-HQ", "192.168.1.1")
    events(collector, [ev("network.config_change", "FW-HQ", user="admin")])
    finding = owner.get("/api/v1/findings").json()["items"][0]
    assert finding["rule_key"] == "firewall_config_changed"
    assert finding["asset_id"] == fw and finding["severity"] == "high"


def test_ids_alerts_by_severity(owner, collector):
    events(
        collector,
        [
            ev(
                "network.ids_alert",
                "192.168.1.40",
                suricata_severity=3,
                signature="ET INFO curl user agent",
            )
        ],
    )
    assert rules(owner) == set()
    events(
        collector,
        [
            ev(
                "network.ids_alert",
                "192.168.1.40",
                suricata_severity=1,
                signature="ET MALWARE beacon",
            )
        ],
    )
    assert rules(owner) == {"network_intrusion_alert"}
    summary = owner.get("/api/v1/network/summary").json()
    assert summary["top_signatures"][0]["name"] in {"ET MALWARE beacon", "ET INFO curl user agent"}


def test_admin_bruteforce_threshold(owner, collector):
    events(
        collector, [ev("network.admin_login_failure", count=4, user="admin", src_ip="203.0.113.7")]
    )
    assert rules(owner) == set()
    events(collector, [ev("network.admin_login_failure", user="admin", src_ip="203.0.113.7")])
    assert rules(owner) == {"network_admin_bruteforce"}


def test_port_scans_from_outside_but_not_inside(owner, collector):
    events(
        collector,
        [
            ev(
                "network.firewall_deny",
                count=600,
                src_ip="192.168.1.50",
                dst_ip="192.168.1.1",
                dst_port="22",
            )
        ],
    )
    assert rules(owner) == set()
    events(
        collector,
        [
            ev("network.firewall_deny", count=300, src_ip="203.0.113.66"),
            ev("network.firewall_deny", count=300, src_ip="203.0.113.66", dst_port="23"),
        ],
    )
    assert rules(owner) == {"port_scan_detected"}
    assert owner.get("/api/v1/network/summary").json()["firewall_denies_24h"] == 1200


def test_zeek_scan_notice(owner, collector):
    events(collector, [ev("network.zeek_notice", "192.168.1.40", note="Scan::Port_Scan")])
    assert rules(owner) == {"port_scan_detected"}


@pytest.mark.parametrize(
    "bad",
    [
        {
            "event_id": "x",
            "event_type": "authentication.failure",
            "timestamp": "2026-01-01T00:00:00Z",
        },
        {
            "event_id": "x",
            "event_type": "network.config_change",
            "timestamp": "2026-01-01T00:00:00Z",
            "organisation_id": "00000000-0000-0000-0000-000000000000",
        },
        {
            "event_id": "x",
            "event_type": "network.firewall_deny",
            "timestamp": "2026-01-01T00:00:00Z",
            "count": 0,
        },
    ],
)
def test_malformed_network_telemetry_is_rejected(collector, bad):
    assert events(collector, [bad]).status_code == 422


def test_network_views_and_isolation(owner, collector):
    assert owner.get("/api/v1/endpoints").json() == []  # collectors aren't endpoints
    collectors = owner.get("/api/v1/network/collectors").json()
    assert len(collectors) == 1 and collectors[0]["online"]
    summary = owner.get("/api/v1/network/summary").json()
    assert summary["collectors_online"] == 1 and summary["sensor_deployed"] is False
    hb(collector, capabilities=["syslog_udp", "suricata"])
    assert owner.get("/api/v1/network/summary").json()["sensor_deployed"] is True

    other = register("eve@other.example.com")
    create_org(other, "Other Ltd")
    assert other.get("/api/v1/network/collectors").json() == []
    assert other.post(f"/api/v1/endpoints/{collectors[0]['id']}/revoke").status_code == 404
    owner.post(f"/api/v1/endpoints/{collectors[0]['id']}/revoke")
    assert hb(collector).status_code == 401
