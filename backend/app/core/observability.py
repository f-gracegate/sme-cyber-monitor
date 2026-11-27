"""Operational visibility for the platform itself: structured logs, metrics, worker heartbeat.

* ``LOG_FORMAT=json`` writes one JSON object per line (timestamp, level, logger, message,
  request id), ready for any log collector. Request bodies, tokens and passwords are never
  logged.
* Request counts and latency buckets are kept in Redis so every API process contributes, and
  ``GET /api/metrics`` (bearer ``METRICS_TOKEN``) serves them in Prometheus text format with
  queue and worker health gauges.
"""

import contextvars
import json
import logging
import socket
import time
from datetime import UTC, datetime

import redis

from app.core.config import settings
from app.core.redis import redis_client

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
LATENCY_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000)
WORKER_KEY = "worker:heartbeat:"
log = logging.getLogger("app.access")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            entry["request_id"] = rid
        for key in ("method", "route", "status", "duration_ms"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    if settings.log_format == "json":
        # Route uvicorn's own messages through the JSON handler too.
        for name in ("uvicorn", "uvicorn.error"):
            logging.getLogger(name).handlers[:] = []
            logging.getLogger(name).propagate = True
    if settings.log_access or settings.log_format == "json":
        # Our access line (route template, duration, request id) replaces uvicorn's.
        logging.getLogger("uvicorn.access").disabled = True


def record_request(method: str, route: str, status: int, duration_ms: float) -> None:
    """Count one request (best effort: metrics must never break a request)."""
    bucket = next((b for b in LATENCY_BUCKETS_MS if duration_ms <= b), "inf")
    try:
        pipe = redis_client.pipeline(transaction=False)
        pipe.hincrby("metrics:requests", f"{method}|{route}|{status}", 1)
        pipe.hincrby("metrics:latency", f"{route}|{bucket}", 1)
        pipe.hincrbyfloat("metrics:latency_sum", route, duration_ms)
        pipe.execute()
    except redis.RedisError:
        pass
    if settings.log_access:
        log.info(
            "%s %s %s %.0fms",
            method,
            route,
            status,
            duration_ms,
            extra={
                "method": method,
                "route": route,
                "status": status,
                "duration_ms": round(duration_ms),
            },
        )


def worker_heartbeat() -> None:
    try:
        redis_client.set(f"{WORKER_KEY}{socket.gethostname()}", int(time.time()), ex=300)
    except redis.RedisError:
        pass


def worker_status() -> tuple[int, float | None]:
    """Number of workers seen in the last 5 minutes and the age of the freshest heartbeat."""
    try:
        keys = list(redis_client.scan_iter(f"{WORKER_KEY}*"))
        stamps = [int(v) for v in redis_client.mget(keys) if v] if keys else []
    except redis.RedisError:
        return 0, None
    if not stamps:
        return 0, None
    return len(stamps), time.time() - max(stamps)


def prometheus_text(gauges: dict[str, float]) -> str:
    lines = [
        "# HELP smecm_http_requests_total API requests by method, route and status.",
        "# TYPE smecm_http_requests_total counter",
    ]
    try:
        requests = redis_client.hgetall("metrics:requests")
        latency = redis_client.hgetall("metrics:latency")
        sums = redis_client.hgetall("metrics:latency_sum")
    except redis.RedisError:
        requests, latency, sums = {}, {}, {}
    for key, value in sorted(requests.items()):
        method, route, status = _s(key).split("|")
        lines.append(
            f'smecm_http_requests_total{{method="{method}",route="{route}",status="{status}"}} '
            f"{int(value)}"
        )
    lines += [
        "# HELP smecm_http_request_duration_ms API latency.",
        "# TYPE smecm_http_request_duration_ms histogram",
    ]
    per_route: dict[str, dict[str, int]] = {}
    for key, value in latency.items():
        route, bucket = _s(key).rsplit("|", 1)
        per_route.setdefault(route, {})[bucket] = int(value)
    for route, buckets in sorted(per_route.items()):
        cumulative = 0
        for b in (*LATENCY_BUCKETS_MS, "inf"):
            cumulative += buckets.get(str(b), 0)
            le = "+Inf" if b == "inf" else str(b)
            lines.append(
                f'smecm_http_request_duration_ms_bucket{{route="{route}",le="{le}"}} {cumulative}'
            )
        lines.append(f'smecm_http_request_duration_ms_count{{route="{route}"}} {cumulative}')
        total = float(_s(sums.get(route.encode(), sums.get(route, 0)) or 0))
        lines.append(f'smecm_http_request_duration_ms_sum{{route="{route}"}} {total:.0f}')
    for name, value in gauges.items():
        lines.append(f"# TYPE smecm_{name} gauge")
        lines.append(f"smecm_{name} {value}")
    return "\n".join(lines) + "\n"


def _s(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)
