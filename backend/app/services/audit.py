import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def record(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    organisation_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    actor_label: str | None = None,
) -> None:
    """Add an audit entry to the current transaction. Commits with the change it describes."""
    db.add(
        AuditLog(
            organisation_id=organisation_id,
            actor_id=actor.id if actor else None,
            actor_label=actor_label or (actor.email if actor else None),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details or {},
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent", "")[:400] or None) if request else None,
            request_id=getattr(request.state, "request_id", None) if request else None,
        )
    )
