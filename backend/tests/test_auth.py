import time

import pyotp
from sqlalchemy import select

from app.core.db import SessionLocal, system_context
from app.models import User
from app.security.passwords import hash_password
from app.services.email import read_dev_mailbox
from tests.conftest import PASSWORD, Api, enable_mfa, register


def login(identifier: str, password: str = PASSWORD) -> tuple[Api, dict]:
    api = Api()
    r = api.post("/api/v1/auth/login", {"identifier": identifier, "password": password})
    return api, {**r.json(), "http": r.status_code}


def test_register_and_me():
    api = register("kofi@example.org", "Kofi Mensah")
    me = api.get("/api/v1/auth/me").json()
    assert me["user"]["email"] == "kofi@example.org"
    assert me["memberships"] == []


def test_register_rejects_duplicate_email_and_weak_password():
    register("dup@example.org")
    r = Api().post(
        "/api/v1/auth/register",
        {"email": "DUP@example.org", "password": PASSWORD, "full_name": "X"},
    )
    assert r.status_code == 409
    r = Api().post(
        "/api/v1/auth/register",
        {"email": "weak@example.org", "password": "password", "full_name": "X"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "weak_password"


def test_login_with_email_or_username_and_wrong_password():
    register("esi@example.org", username="esi.b")
    assert login("esi@example.org")[1]["http"] == 200
    assert login("ESI.B")[1]["http"] == 200
    _, body = login("esi@example.org", "wrong-password-123")
    assert body["http"] == 401
    assert body["error"]["code"] == "invalid_credentials"
    # Unknown accounts get the same answer as wrong passwords.
    assert login("nobody@example.org")[1]["error"]["code"] == "invalid_credentials"


def test_account_locks_after_repeated_failures():
    register("lock@example.org")
    for _ in range(5):
        assert login("lock@example.org", "nope-nope-nope")[1]["http"] == 401
    _, body = login("lock@example.org")  # even the right password is refused while locked
    assert body["http"] == 423


def test_forced_password_change_blocks_everything_else():
    db = SessionLocal()
    db.info["rls"] = {}
    with system_context(db):
        db.add(
            User(
                email="temp@example.org",
                username="Temp",
                full_name="Temp",
                password_hash=hash_password("password"),
                must_change_password=True,
            )
        )
        db.commit()
    db.close()

    api, body = login("Temp", "password")
    assert body["me"]["user"]["must_change_password"] is True
    assert api.get("/api/v1/organisations").json()["error"]["code"] == "password_change_required"
    r = api.post(
        "/api/v1/auth/password/change", {"current_password": "password", "new_password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    assert api.get("/api/v1/organisations").status_code == 200


def test_cookie_requests_need_csrf_token():
    api = register("csrf@example.org")
    r = api.client.post("/api/v1/organisations", json={"name": "No Token Ltd"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_logout_revokes_session():
    api = register("bye@example.org")
    access = api.client.cookies.get("smecm_access")
    assert api.post("/api/v1/auth/logout").status_code == 200
    replay = Api()
    r = replay.client.get("/api/v1/auth/me", headers={"authorization": f"Bearer {access}"})
    assert r.status_code == 401


def test_refresh_rotates_and_detects_reuse():
    api = register("rot@example.org")
    old_refresh = api.client.cookies.get("smecm_refresh")
    assert api.post("/api/v1/auth/refresh").status_code == 200
    assert api.client.cookies.get("smecm_refresh") != old_refresh

    attacker = Api()
    attacker.client.cookies.set("smecm_refresh", old_refresh, path="/api/v1/auth")
    assert attacker.post("/api/v1/auth/refresh").status_code == 401
    # Reuse of the stolen token ends the legitimate session too.
    assert api.get("/api/v1/auth/me").status_code == 401


def test_mfa_login_flow_replay_and_recovery_codes():
    api = register("mfa@example.org")
    totp = enable_mfa(api)

    _, body = login("mfa@example.org")
    assert body["http"] == 200 and body["status"] == "mfa_required" and body["mfa_token"]
    client = Api()
    # The code used to switch MFA on is spent, so sign in with the next time-step's code.
    code = totp.at(int(time.time()) + 30)
    r = client.post("/api/v1/auth/mfa/verify", {"mfa_token": body["mfa_token"], "code": code})
    assert r.status_code == 200, r.text
    assert r.json()["me"]["user"]["mfa_enabled"] is True

    # The same code cannot be used twice.
    _, body = login("mfa@example.org")
    r = Api().post("/api/v1/auth/mfa/verify", {"mfa_token": body["mfa_token"], "code": code})
    assert r.status_code == 401

    # Recovery codes work exactly once.
    api2 = register("mfa2@example.org")
    r = api2.post("/api/v1/auth/mfa/setup")
    secret = r.json()["secret"]
    codes = api2.post("/api/v1/auth/mfa/enable", {"code": pyotp.TOTP(secret).now()}).json()[
        "recovery_codes"
    ]
    for expected in (200, 401):
        _, body = login("mfa2@example.org")
        r = Api().post(
            "/api/v1/auth/mfa/verify", {"mfa_token": body["mfa_token"], "code": codes[0]}
        )
        assert r.status_code == expected


def test_password_reset_flow_and_session_revocation():
    api = register("reset@example.org")
    r = Api().post("/api/v1/auth/password/forgot", {"email": "reset@example.org"})
    assert r.status_code == 202
    # Unknown emails get the same response.
    assert (
        Api().post("/api/v1/auth/password/forgot", {"email": "ghost@example.org"}).status_code
        == 202
    )
    link = next(m for m in read_dev_mailbox() if m["to"] == "reset@example.org")["body"]
    token = link.split("token=")[1].split()[0]
    new = "Brand-New-Passphrase-7"
    assert (
        Api().post("/api/v1/auth/password/reset", {"token": token, "new_password": new}).status_code
        == 200
    )
    assert api.get("/api/v1/auth/me").status_code == 401  # old sessions ended
    assert login("reset@example.org", new)[1]["http"] == 200
    # Reset links are single use.
    assert (
        Api()
        .post(
            "/api/v1/auth/password/reset", {"token": token, "new_password": "Another-Passphrase-8"}
        )
        .status_code
        == 400
    )


def test_mfa_secret_is_encrypted_at_rest():
    api = register("enc@example.org")
    enable_mfa(api)
    db = SessionLocal()
    db.info["rls"] = {}
    user = db.scalar(select(User).where(User.email == "enc@example.org"))
    assert user.mfa_secret_encrypted and len(user.mfa_secret_encrypted) > 60
    assert all(h.startswith("$argon2id$") for h in user.mfa_recovery_code_hashes)
    db.close()
