"""Wazuh connector: map Wazuh alerts to our normalised endpoint events.

Wazuh does the heavy lifting on the device (log collection, rootcheck, file integrity, malware
and Windows event analysis). A small integration script on the Wazuh manager forwards alerts to
``POST /api/v1/integrations/wazuh/alerts`` with an organisation integration key. This module
decides what each alert means in our vocabulary.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

MIN_LEVEL = 3  # Wazuh levels 0-2 are noise for our purposes.

_AUTH_FAIL = {
    "authentication_failed",
    "authentication_failures",
    "win_authentication_failed",
    "invalid_login",
}
_AUTH_OK = {"authentication_success"}
_MALWARE = {"virus", "malware", "rootkit", "trojan"}
_ACCOUNT = {"adduser", "group_changed", "group_created", "account_changed"}
_SUSPICIOUS = {
    "attack",
    "exploit_attempt",
    "web_attack",
    "sql_injection",
    "shellshock",
    "mitre_execution",
}
_USB = {"usb", "removable_media"}


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        # Wazuh writes "+0000"; Python wants "+00:00".
        if len(text) > 5 and text[-5] in "+-" and text[-4:].isdigit():
            text = f"{text[:-2]}:{text[-2:]}"
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _severity(level: int) -> str:
    if level >= 12:
        return "high"
    if level >= 7:
        return "medium"
    if level >= 4:
        return "low"
    return "informational"


def agent_identity(alert: dict[str, Any]) -> dict[str, str] | None:
    agent = alert.get("agent")
    if not isinstance(agent, dict) or not agent.get("id"):
        return None
    return {
        "id": str(agent["id"])[:128],
        "name": str(agent.get("name") or f"wazuh-agent-{agent['id']}")[:255],
        "ip": str(agent.get("ip") or "")[:64] or None,
    }


def map_alert(alert: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalised event dict (EventIn shape) or None to ignore the alert."""
    rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
    try:
        level = int(rule.get("level", 0))
    except (TypeError, ValueError):
        level = 0
    if level < MIN_LEVEL:
        return None
    groups = {str(g).lower() for g in rule.get("groups", []) if g}
    description = str(rule.get("description") or "Wazuh alert")[:300]
    data = alert.get("data") if isinstance(alert.get("data"), dict) else {}
    win = _get(data, "win", "eventdata") or {}
    account = (
        data.get("dstuser")
        or data.get("srcuser")
        or win.get("targetUserName")
        or win.get("subjectUserName")
    )
    source_ip = data.get("srcip") or win.get("ipAddress")
    virustotal_hit = str(_get(data, "virustotal", "malicious")) == "1"

    if groups & _AUTH_FAIL:
        event_type = "authentication.failure"
    elif groups & _AUTH_OK:
        event_type = "authentication.success"
    elif groups & _MALWARE or virustotal_hit or ("windows_defender" in groups and level >= 12):
        event_type = "malware.detected"
    elif groups & _ACCOUNT and "admin" in description.lower():
        event_type = "account.privileged_created"
    elif (
        "logs_cleared" in groups
        or "log was cleared" in description.lower()
        or "log file was cleared" in description.lower()
    ):
        event_type = "log.cleared"
    elif groups & _USB:
        event_type = "removable_media.connected"
    elif groups & _SUSPICIOUS and level >= 10:
        event_type = "process.suspicious"
    elif "syscheck" in groups:
        event_type = "file_integrity.changed"
    else:
        event_type = "generic"

    severity = {
        "malware.detected": "critical",
        "authentication.failure": "low",
        "authentication.success": "informational",
    }.get(event_type, _severity(level))

    event_id = str(alert.get("id") or "")
    if not event_id:
        event_id = hashlib.sha256(
            json.dumps(alert, sort_keys=True, default=str).encode()
        ).hexdigest()
    details = {
        "engine": "wazuh",
        "engine_rule_id": str(rule.get("id") or ""),
        "engine_level": level,
        "description": description,
        "groups": sorted(groups)[:10],
    }
    if account:
        details["account"] = str(account)[:120]
    if source_ip:
        details["source_ip"] = str(source_ip)[:64]
    path = _get(alert, "syscheck", "path")
    if path:
        details["path"] = str(path)[:300]
    return {
        "event_id": f"wazuh:{event_id}"[:128],
        "event_type": event_type,
        "timestamp": _timestamp(alert.get("timestamp")),
        "severity": severity,
        "summary": description,
        "data": details,
    }
