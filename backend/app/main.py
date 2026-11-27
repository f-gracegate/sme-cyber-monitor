import hmac
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.api.v1 import (
    assets,
    auth,
    billing,
    devices,
    endpoints,
    incidents,
    monitoring,
    network,
    onboarding,
    organisations,
    pilot,
    privacy,
    reports,
    workspace,
)
from app.core.config import settings
from app.core.db import engine
from app.core.errors import APIError, register_error_handlers
from app.core.observability import (
    configure_logging,
    prometheus_text,
    record_request,
    request_id_var,
    worker_status,
)
from app.core.redis import redis_client

configure_logging()

app = FastAPI(
    title=f"{settings.brand_product_name} API",
    version="0.1.0",
    description="Multi-tenant API for business cybersecurity visibility, monitoring and risk "
    "management. Organisation-scoped endpoints need the X-Organisation-Id header.",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
)
register_error_handlers(app)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request.state.request_id = incoming[:64] if incoming else uuid.uuid4().hex
    token = request_id_var.set(request.state.request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    route = getattr(request.scope.get("route"), "path", None)
    # The route template (/api/v1/alerts/{alert_id}), never the raw path with IDs in it.
    if route and not route.startswith("/api"):
        route = "/api/v1" + route
    record_request(
        request.method,
        route or "unmatched",
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    response.headers["X-Request-ID"] = request.state.request_id
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if not settings.is_development:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


for module in (
    auth,
    organisations,
    assets,
    monitoring,
    endpoints,
    network,
    incidents,
    reports,
    workspace,
    billing,
    devices,
    onboarding,
    pilot,
    privacy,
):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/api/health", tags=["Health"])
def health() -> dict:
    status = {"database": "ok", "redis": "ok"}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        status["database"] = "unavailable"
    try:
        redis_client.ping()
    except Exception:  # noqa: BLE001
        status["redis"] = "unavailable"
    workers, age = worker_status()
    status["worker"] = "ok" if workers and age is not None and age < 120 else "stale"
    healthy = status["database"] == "ok" and status["redis"] == "ok"
    return {"status": "ok" if healthy else "degraded", **status}


@app.get("/api/metrics", include_in_schema=False)
def metrics(request: Request) -> PlainTextResponse:
    """Prometheus metrics. Requires METRICS_TOKEN; disabled when it isn't set."""
    sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not settings.metrics_token or not hmac.compare_digest(sent, settings.metrics_token):
        raise APIError(404, "not_found", "Not found.")
    from app.ops.gauges import collect_gauges

    return PlainTextResponse(prometheus_text(collect_gauges()), media_type="text/plain")
