"""Load tests for the performance targets in the product plan.

Run inside the development stack (it uses the development mailbox and adjusts one test
organisation's plan directly in the database, so never point it at production):

    docker compose exec backend python -m app.ops.loadtest --users 20 --seconds 60 --agents 20

Measures:

1. **Dashboard API** under concurrent use: p50/p95/p99 per endpoint (target p95 < 500 ms).
2. **Event ingestion burst** (security scenario 8): many agents sending full batches at once.
   Accepted events per second, rejections (429 is the designed back-pressure), and errors
   (must be zero 5xx).
3. **Alert delivery**: time from the events that trigger a brute-force detection to the alert
   being visible (target: within 2 minutes).
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import update

from app.core.db import SessionLocal
from app.models import Subscription
from app.schemas.endpoint import MAX_EVENTS_PER_BATCH

PASSWORD = "Load-Test-Password-42!"  # noqa: S105 - throwaway account in a dev database
DASHBOARD = ["/overview", "/alerts", "/incidents", "/assets", "/findings", "/remediation-tasks"]


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


async def setup(base: str) -> tuple[httpx.AsyncClient, str]:
    email = f"load-{uuid.uuid4().hex[:8]}@example.com"
    client = httpx.AsyncClient(base_url=base, timeout=30)
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Load Test"},
    )
    r.raise_for_status()
    csrf = client.cookies.get("smecm_csrf")
    client.headers["x-csrf-token"] = csrf
    mail = next(m for m in (await client.get("/api/v1/dev/mailbox")).json() if m["to"] == email)
    token = mail["body"].split("verify-email?token=")[1].split()[0]
    (await client.post("/api/v1/auth/email/verify", json={"token": token})).raise_for_status()
    org = (await client.post("/api/v1/organisations", json={"name": "Load Test Ltd"})).json()
    client.headers["x-organisation-id"] = org["id"]
    # Room for many agents: this is a test organisation in a development database.
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    db.execute(
        update(Subscription)
        .where(Subscription.organisation_id == uuid.UUID(org["id"]))
        .values(plan_code="enterprise", status="active")
    )
    db.commit()
    db.close()
    for i in range(10):
        await client.post(
            "/api/v1/assets",
            json={"name": f"Site {i}", "type": "website", "identifier": f"site{i}.example.com"},
        )
    return client, org["id"]


async def dashboard(client: httpx.AsyncClient, users: int, seconds: int) -> dict:
    timings: dict[str, list[float]] = {p: [] for p in DASHBOARD}
    errors = 0
    deadline = time.monotonic() + seconds

    async def user(n: int) -> None:
        nonlocal errors
        i = n
        while time.monotonic() < deadline:
            path = DASHBOARD[i % len(DASHBOARD)]
            i += 1
            start = time.perf_counter()
            r = await client.get(f"/api/v1{path}")
            timings[path].append((time.perf_counter() - start) * 1000)
            if r.status_code >= 400:
                errors += 1

    await asyncio.gather(*(user(n) for n in range(users)))
    rows = {
        path: {
            "requests": len(t),
            "p50_ms": round(pct(t, 50)),
            "p95_ms": round(pct(t, 95)),
            "p99_ms": round(pct(t, 99)),
        }
        for path, t in timings.items()
    }
    total = sum(len(t) for t in timings.values())
    return {
        "endpoints": rows,
        "requests": total,
        "requests_per_second": round(total / seconds, 1),
        "errors": errors,
        "p95_ms_overall": round(pct([x for t in timings.values() for x in t], 95)),
    }


def event(i: int, kind: str = "process") -> dict:
    now = datetime.now(UTC).isoformat()
    if kind == "failure":
        return {
            "event_id": f"bf-{i}-{uuid.uuid4().hex[:8]}",
            "event_type": "authentication.failure",
            "timestamp": now,
            "data": {"account": "administrator", "source_ip": "203.0.113.50"},
        }
    return {
        "event_id": f"ev-{i}-{uuid.uuid4().hex[:8]}",
        "event_type": "authentication.success",
        "timestamp": now,
        "data": {"account": f"user{i % 7}", "source_ip": "192.0.2.10"},
    }


async def ingestion(client: httpx.AsyncClient, base: str, agents: int, batches: int) -> dict:
    r = await client.post(
        "/api/v1/endpoints/enrolment-tokens",
        json={"asset_type": "workstation", "max_uses": min(500, agents), "valid_hours": 1},
    )
    r.raise_for_status()
    token = r.json()["token"]
    device = httpx.AsyncClient(base_url=base, timeout=30)
    creds = []
    for n in range(agents):
        r = await device.post(
            "/api/v1/agent/enrol",
            json={
                "token": token,
                "machine_id": f"load-{uuid.uuid4().hex}",
                "agent_version": "1.0.0",
                "inventory": {
                    "hostname": f"LOAD-PC-{n:03d}",
                    "os_family": "windows",
                    "os_name": "Windows 11 Pro",
                    "firewall_enabled": True,
                    "antivirus_enabled": True,
                    "disk_encrypted": True,
                },
            },
        )
        r.raise_for_status()
        creds.append(r.json()["credential"])

    statuses: dict[int, int] = {}
    latencies: list[float] = []
    accepted = 0

    async def agent(cred: str, n: int) -> None:
        nonlocal accepted
        for b in range(batches):
            events = [event(n * 100_000 + b * 1000 + i) for i in range(MAX_EVENTS_PER_BATCH)]
            start = time.perf_counter()
            r = await device.post(
                "/api/v1/agent/events",
                headers={"Authorization": f"Agent {cred}"},
                json={"events": events},
            )
            latencies.append((time.perf_counter() - start) * 1000)
            statuses[r.status_code] = statuses.get(r.status_code, 0) + 1
            if r.status_code == 200:
                accepted += r.json()["accepted"]

    start = time.perf_counter()
    await asyncio.gather(*(agent(c, n) for n, c in enumerate(creds)))
    elapsed = time.perf_counter() - start

    # Alert delivery: a brute-force burst from one agent, then wait for the alert.
    burst = [event(i, "failure") for i in range(15)]
    sent_at = time.perf_counter()
    await device.post(
        "/api/v1/agent/events",
        headers={"Authorization": f"Agent {creds[0]}"},
        json={"events": burst},
    )
    alert_seconds = None
    for _ in range(240):
        alerts = (await client.get("/api/v1/alerts")).json()["items"]
        if any("sign-in" in a["title"].lower() or "brute" in a["title"].lower() for a in alerts):
            alert_seconds = round(time.perf_counter() - sent_at, 2)
            break
        await asyncio.sleep(0.5)
    await device.aclose()
    return {
        "agents": agents,
        "batches_sent": sum(statuses.values()),
        "events_per_batch": MAX_EVENTS_PER_BATCH,
        "status_codes": statuses,
        "server_errors": sum(n for s, n in statuses.items() if s >= 500),
        "accepted_events": accepted,
        "accepted_events_per_second": round(accepted / elapsed, 1),
        "batch_p95_ms": round(pct(latencies, 95)),
        "batch_median_ms": round(statistics.median(latencies)) if latencies else 0,
        "alert_visible_after_seconds": alert_seconds,
    }


async def main(args: argparse.Namespace) -> None:
    client, org_id = await setup(args.base)
    print(f"test organisation {org_id}")
    results = {
        "dashboard": await dashboard(client, args.users, args.seconds),
        "ingestion": await ingestion(client, args.base, args.agents, args.batches),
    }
    await client.aclose()
    print(json.dumps(results, indent=2))
    d, i = results["dashboard"], results["ingestion"]
    verdicts = [
        ("API p95 below 500 ms", d["p95_ms_overall"] < 500),
        ("no dashboard errors", d["errors"] == 0),
        ("no 5xx during the ingestion burst", i["server_errors"] == 0),
        (
            "alert within 2 minutes",
            i["alert_visible_after_seconds"] is not None and i["alert_visible_after_seconds"] < 120,
        ),
    ]
    for name, ok in verdicts:
        print(("PASS " if ok else "FAIL ") + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--agents", type=int, default=20)
    parser.add_argument("--batches", type=int, default=10)
    asyncio.run(main(parser.parse_args()))
