"""Monitoring worker: claims due checks and runs them.

    python -m app.workers.monitor

Several workers can run side by side. Each claim moves a check's next_run_at forward inside a
`FOR UPDATE SKIP LOCKED` statement, so a check is never run twice at once, and a worker that
crashes mid-run simply leaves the check to run again at its next interval.
"""

import logging
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.billing.service import sweep_subscriptions
from app.core.db import SessionLocal
from app.core.observability import configure_logging, worker_heartbeat
from app.endpoints.service import sweep_offline
from app.monitoring.engine import execute_check
from app.privacy.service import prune_telemetry, run_due_erasures
from app.reports.service import generate_monthly_reports
from app.services.email import send_email
from app.services.push import dispatch_pending

log = logging.getLogger("app.workers.monitor")

POLL_SECONDS = 10
BATCH = 16
CONCURRENCY = 8
RUN_RETENTION_DAYS = 30

_CLAIM = text("""
    UPDATE monitoring_checks AS c
       SET next_run_at = now() + make_interval(mins => c.interval_minutes)
     WHERE c.id IN (
        SELECT mc.id
          FROM monitoring_checks mc
          JOIN assets a ON a.id = mc.asset_id
         WHERE mc.enabled
           AND mc.check_type NOT IN
               ('endpoint_health', 'agent_heartbeat', 'device_availability', 'collector_health')
           AND mc.next_run_at <= now()
           AND a.status = 'active'
           AND a.monitoring_status IN ('authorised', 'monitoring', 'degraded')
         ORDER BY mc.next_run_at
         LIMIT :limit
         FOR UPDATE OF mc SKIP LOCKED)
    RETURNING c.id
""")


def claim_due(limit: int = BATCH) -> list[uuid.UUID]:
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        ids = list(db.execute(_CLAIM, {"limit": limit}).scalars())
        db.commit()
        return ids
    finally:
        db.close()


def prune_old_runs() -> int:
    """Apply each organisation's retention setting, and erase organisations that are due."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        erased = run_due_erasures(db)
        if erased:
            log.info("erased %d organisation(s) after their cooling-off period", erased)
        return prune_telemetry(db)
    finally:
        db.close()


def check_offline_agents() -> int:
    """Flag devices whose agent stopped sending heartbeats."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        emails = sweep_offline(db)
        db.commit()
    finally:
        db.close()
    for job in emails:
        send_email(job.to, job.subject, job.body)
    return len(emails)


def run_scheduled_reports() -> int:
    """Monthly executive reports (idempotent, so running it every hour is safe)."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        return generate_monthly_reports(db)
    finally:
        db.close()


def send_pushes() -> int:
    """Turn new in-app notifications into phone pushes."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        return dispatch_pending(db)
    finally:
        db.close()


def run_billing_sweep() -> int:
    """Move subscriptions through trial/active/past due/expired and send renewal reminders."""
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        return sweep_subscriptions(db)
    finally:
        db.close()


def main() -> None:
    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)  # per-request lines are noise here
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    log.info("monitoring worker started (concurrency=%s)", CONCURRENCY)
    last_prune = 0.0
    last_sweep = 0.0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        while not stop.is_set():
            try:
                worker_heartbeat()
                ids = claim_due()
                if ids:
                    log.info("running %d check(s)", len(ids))
                    list(pool.map(execute_check, ids))
                pushed = send_pushes()
                if pushed:
                    log.info("sent %d push notification(s)", pushed)
                if time.monotonic() - last_sweep > 60:
                    check_offline_agents()
                    last_sweep = time.monotonic()
                if time.monotonic() - last_prune > 3600:
                    reminders = run_billing_sweep()
                    if reminders:
                        log.info("sent %d billing email(s)", reminders)
                    created = run_scheduled_reports()
                    if created:
                        log.info("generated %d monthly report(s)", created)
                    pruned = prune_old_runs()
                    if pruned:
                        log.info("pruned %d old check runs", pruned)
                    last_prune = time.monotonic()
            except Exception:  # noqa: BLE001 - keep the worker alive through DB blips
                log.exception("worker loop error")
            stop.wait(POLL_SECONDS)
    log.info("monitoring worker stopped")


if __name__ == "__main__":
    main()
