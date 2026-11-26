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
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text

from app.core.db import SessionLocal
from app.models import CheckRun
from app.monitoring.engine import execute_check

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
    db = SessionLocal()
    db.info["rls"] = {"bypass": True}
    try:
        cutoff = datetime.now(UTC) - timedelta(days=RUN_RETENTION_DAYS)
        deleted = db.execute(delete(CheckRun).where(CheckRun.completed_at < cutoff)).rowcount
        db.commit()
        return deleted or 0
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # per-request lines are noise here
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    log.info("monitoring worker started (concurrency=%s)", CONCURRENCY)
    last_prune = 0.0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        while not stop.is_set():
            try:
                ids = claim_due()
                if ids:
                    log.info("running %d check(s)", len(ids))
                    list(pool.map(execute_check, ids))
                if time.monotonic() - last_prune > 3600:
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
