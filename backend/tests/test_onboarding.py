from tests.conftest import invite_and_join
from tests.test_monitoring_engine import authorised_website


def steps(api) -> dict:
    data = api.get("/api/v1/onboarding").json()
    return {s["id"]: s for s in data["steps"]} | {"_": data}


def test_checklist_follows_the_business_onboarding_journey(owner, monkeypatch):
    s = steps(owner)
    assert s["_"]["required"] == 6 and s["_"]["required_done"] == 0
    assert not s["_"]["complete"] and not s["_"]["dismissed"]
    assert s["endpoint"]["optional"] and s["mobile"]["optional"] and s["plan"]["optional"]

    org = owner.get(f"/api/v1/organisations/{owner.org_id}").json()
    r = owner.client.patch(
        f"/api/v1/organisations/{owner.org_id}",
        json={**{k: org[k] for k in ("name", "industry")}, "phone": "+233 30 000 0000"},
        headers=owner._headers(),
    )
    assert r.status_code == 200, r.text
    assert steps(owner)["profile"]["done"]

    authorised_website(owner, monkeypatch)
    s = steps(owner)
    assert s["asset"]["done"] and s["verify"]["done"] and not s["monitoring"]["done"]

    invite_and_join(owner, "it@acme.example.com", "it_admin")
    assert steps(owner)["team"]["done"]


def test_admin_can_dismiss_but_staff_cannot(owner):
    staff = invite_and_join(owner, "staff@acme.example.com", "employee")
    s = steps(staff)
    assert "plan" not in s  # staff can't see billing
    r = staff.client.put(
        "/api/v1/onboarding/dismissed", json={"dismissed": True}, headers=staff._headers()
    )
    assert r.status_code == 403
    r = owner.client.put(
        "/api/v1/onboarding/dismissed", json={"dismissed": True}, headers=owner._headers()
    )
    assert r.status_code == 200 and r.json()["dismissed"] is True
