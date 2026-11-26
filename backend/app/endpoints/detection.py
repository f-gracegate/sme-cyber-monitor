"""Detection rules for endpoint security events.

* Direct rules: one event is enough (malware, log cleared, new admin account, ...).
* Threshold rules: many failed sign-ins in a short window. One failed sign-in is normal and is
  never treated as an intrusion.
* Sequence rule: a successful sign-in to an account right after a burst of failures.

Detections are "sticky" findings: they stay open until a person reviews them.
"""

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SecurityEvent
from app.monitoring.checks import Issue

FAILED_LOGIN_WINDOW = timedelta(minutes=10)
FAILED_LOGIN_THRESHOLD = 10

DIRECT_RULES = {
    "malware.detected": "malware_detected",
    "protection.disabled": "protection_tampering",
    "account.privileged_created": "privileged_account_created",
    "log.cleared": "security_log_cleared",
    "process.suspicious": "suspicious_process",
    "removable_media.connected": "removable_media_used",
}

DEFAULT_SEVERITY = {
    "authentication.failure": "low",
    "authentication.success": "informational",
    "malware.detected": "critical",
    "protection.disabled": "high",
    "account.privileged_created": "high",
    "log.cleared": "high",
    "process.suspicious": "high",
    "removable_media.connected": "low",
    "file_integrity.changed": "low",
    "generic": "informational",
}

DEFAULT_SUMMARY = {
    "authentication.failure": "Failed sign-in",
    "authentication.success": "Successful sign-in",
    "malware.detected": "Malware detected",
    "protection.disabled": "Security protection disabled",
    "account.privileged_created": "Administrator account created or changed",
    "log.cleared": "Security log cleared",
    "process.suspicious": "Suspicious process",
    "removable_media.connected": "Removable storage connected",
    "file_integrity.changed": "Monitored file changed",
    "generic": "Endpoint event",
}


def _evidence(event: SecurityEvent) -> dict:
    return {
        "summary": event.summary,
        "occurred_at": event.occurred_at.isoformat(),
        **{
            k: v
            for k, v in (event.data or {}).items()
            if k
            in {
                "account",
                "source_ip",
                "process",
                "path",
                "threat",
                "device",
                "rule",
                "description",
                "product",
                "command_line",
                "engine_rule_id",
                "engine_level",
            }
        },
    }


def _failures(db: Session, asset_id, since: datetime, until: datetime, account: str | None = None):
    stmt = select(SecurityEvent).where(
        SecurityEvent.asset_id == asset_id,
        SecurityEvent.event_type == "authentication.failure",
        SecurityEvent.occurred_at >= since,
        SecurityEvent.occurred_at <= until,
    )
    if account:
        stmt = stmt.where(func.lower(SecurityEvent.data["account"].astext) == account.lower())
    return list(db.scalars(stmt))


def detect(db: Session, asset_id, new_events: list[SecurityEvent]) -> list[Issue]:
    issues: dict[str, Issue] = {}

    for event in sorted(new_events, key=lambda e: e.occurred_at):
        rule = DIRECT_RULES.get(event.event_type)
        if rule:
            issues[rule] = Issue(rule, _evidence(event))
        elif event.event_type == "generic" and event.severity in {"high", "critical"}:
            issues["high_severity_endpoint_alert"] = Issue(
                "high_severity_endpoint_alert", _evidence(event)
            )

    failures_in_batch = [e for e in new_events if e.event_type == "authentication.failure"]
    if failures_in_batch:
        latest = max(e.occurred_at for e in failures_in_batch)
        recent = _failures(db, asset_id, latest - FAILED_LOGIN_WINDOW, latest)
        if len(recent) >= FAILED_LOGIN_THRESHOLD:
            accounts = Counter((e.data or {}).get("account") or "unknown" for e in recent)
            sources = Counter((e.data or {}).get("source_ip") or "unknown" for e in recent)
            issues["repeated_failed_logins"] = Issue(
                "repeated_failed_logins",
                {
                    "failed_attempts": len(recent),
                    "window_minutes": int(FAILED_LOGIN_WINDOW.total_seconds() // 60),
                    "accounts": [a for a, _ in accounts.most_common(5)],
                    "sources": [s for s, _ in sources.most_common(5)],
                },
            )

    for success in (e for e in new_events if e.event_type == "authentication.success"):
        account = (success.data or {}).get("account")
        if not account:
            continue
        prior = _failures(
            db, asset_id, success.occurred_at - FAILED_LOGIN_WINDOW, success.occurred_at, account
        )
        if len(prior) >= FAILED_LOGIN_THRESHOLD:
            issues["login_after_failed_attempts"] = Issue(
                "login_after_failed_attempts",
                {
                    "account": account,
                    "failed_attempts_before": len(prior),
                    "signed_in_at": success.occurred_at.isoformat(),
                    "source_ip": (success.data or {}).get("source_ip"),
                },
            )

    return list(issues.values())
