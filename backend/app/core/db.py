"""Database engine, sessions and the tenant context used by PostgreSQL Row-Level Security.

Every transaction sets three transaction-local settings that the RLS policies read:

* ``app.current_org``  – the organisation the request is acting in
* ``app.current_user`` – the authenticated user (lets users see their own memberships)
* ``app.rls_bypass``   – "on" only inside trusted system code paths (seed, token lookups)

The values are applied with ``set_config(..., is_local => true)`` so they can never leak
between pooled connections.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

_SET_CONTEXT = text(
    "SELECT set_config('app.current_org', :org, true),"
    " set_config('app.current_user', :user, true),"
    " set_config('app.rls_bypass', :bypass, true)"
)


def _context_params(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "org": str(ctx.get("org") or ""),
        "user": str(ctx.get("user") or ""),
        "bypass": "on" if ctx.get("bypass") else "off",
    }


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction: Any, connection: Any) -> None:
    ctx = session.info.get("rls", {})
    connection.execute(_SET_CONTEXT, _context_params(ctx))


def set_tenant_context(db: Session, **values: Any) -> None:
    """Update the tenant context and apply it to the open transaction immediately."""
    ctx = db.info.setdefault("rls", {})
    ctx.update(values)
    if db.in_transaction():
        db.connection().execute(_SET_CONTEXT, _context_params(ctx))


@contextmanager
def system_context(db: Session) -> Iterator[Session]:
    """Temporarily bypass RLS for a trusted, narrowly scoped system operation."""
    previous = db.info.get("rls", {}).get("bypass", False)
    set_tenant_context(db, bypass=True)
    try:
        yield db
    finally:
        set_tenant_context(db, bypass=previous)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    db.info["rls"] = {}
    try:
        yield db
    finally:
        db.close()
