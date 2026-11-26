import logging
import uuid

from fastapi import FastAPI, Request
from sqlalchemy import text

from app.api.v1 import assets, auth, monitoring, organisations, workspace
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.redis import redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

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
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if not settings.is_development:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


for module in (auth, organisations, assets, monitoring, workspace):
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
    return {"status": "ok" if all(v == "ok" for v in status.values()) else "degraded", **status}
