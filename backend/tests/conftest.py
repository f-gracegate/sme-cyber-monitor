"""Test setup: a dedicated database and Redis DB, migrated once and truncated between tests.

Run inside the dev stack:  docker compose run --rm backend pytest
"""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://smecm_app:smecm_app_dev@localhost:5532/smecm_test"
)
os.environ["MIGRATION_DATABASE_URL"] = os.environ.get(
    "TEST_MIGRATION_DATABASE_URL",
    "postgresql+psycopg://smecm_owner:smecm_owner_dev@localhost:5532/smecm_test",
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6479/1")
os.environ.pop("ALEMBIC_DATABASE_URL", None)

import pyotp  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture(scope="session")
def owner_engine():
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(settings.migration_database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_state(owner_engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with owner_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    redis_client.flushdb()
    yield


class Api:
    """A signed-in browser: keeps cookies, sends the CSRF header and the organisation header."""

    def __init__(self) -> None:
        self.client = TestClient(app)
        self.org_id: str | None = None

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {}
        csrf = self.client.cookies.get("smecm_csrf")
        if csrf:
            headers["x-csrf-token"] = csrf
        if self.org_id:
            headers["x-organisation-id"] = self.org_id
        headers.update(extra or {})
        return headers

    def get(self, url, **kw):
        return self.client.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(
            url, json=json, headers=self._headers(kw.pop("headers", None)), **kw
        )

    def patch(self, url, json=None, **kw):
        return self.client.patch(
            url, json=json, headers=self._headers(kw.pop("headers", None)), **kw
        )

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)


def register(email: str, name: str = "Test User", password: str = PASSWORD, **extra) -> Api:
    api = Api()
    r = api.post(
        "/api/v1/auth/register", {"email": email, "password": password, "full_name": name, **extra}
    )
    assert r.status_code == 201, r.text
    return api


def create_org(api: Api, name: str = "Acme Ltd") -> str:
    r = api.post("/api/v1/organisations", {"name": name, "industry": "retail"})
    assert r.status_code == 201, r.text
    api.org_id = r.json()["id"]
    return api.org_id


def invite_and_join(owner: Api, email: str, role: str) -> Api:
    r = owner.post(
        f"/api/v1/organisations/{owner.org_id}/invitations", {"email": email, "role": role}
    )
    assert r.status_code == 201, r.text
    token = r.json()["invite_url"].rsplit("/", 1)[1]
    member = register(email, invitation_token=token)
    member.org_id = owner.org_id
    return member


def enable_mfa(api: Api) -> pyotp.TOTP:
    r = api.post("/api/v1/auth/mfa/setup")
    assert r.status_code == 200, r.text
    totp = pyotp.TOTP(r.json()["secret"])
    r = api.post("/api/v1/auth/mfa/enable", {"code": totp.now()})
    assert r.status_code == 200, r.text
    return totp


@pytest.fixture
def owner() -> Api:
    api = register("owner@acme.example.com", "Ama Owner")
    create_org(api)
    return api
