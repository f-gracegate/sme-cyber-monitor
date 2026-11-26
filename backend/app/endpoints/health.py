"""Turn a device's inventory into health findings. Pure functions, unit-tested.

Unknown values (None) never create findings: the agent couldn't tell, so we don't guess.
"""

import re
from typing import Any

from app.monitoring.checks import Issue, Outcome

# Operating systems without security fixes as of late 2026. Review this list every quarter.
_UNSUPPORTED_WINDOWS = re.compile(r"windows\s+(xp|vista|7|8(\.1)?|10)\b", re.I)
_MIN_MACOS_MAJOR = 15
_MIN_UBUNTU = (22, 4)


def unsupported_os(family: str | None, name: str | None, version: str | None) -> bool:
    name = name or ""
    version = version or ""
    if family == "windows":
        if "server" in name.lower():
            return bool(re.search(r"\b(2003|2008|2012)\b", name))
        return bool(_UNSUPPORTED_WINDOWS.search(name))
    if family == "macos":
        match = re.match(r"(\d+)", version)
        return bool(match) and int(match.group(1)) < _MIN_MACOS_MAJOR
    if family == "linux" and "ubuntu" in name.lower():
        match = re.match(r"(\d+)\.(\d+)", version)
        return bool(match) and (int(match.group(1)), int(match.group(2))) < _MIN_UBUNTU
    return False


def evaluate_inventory(inv: dict[str, Any], asset_type: str) -> Outcome:
    issues: list[Issue] = []
    if inv.get("antivirus_enabled") is False:
        issues.append(Issue("antivirus_disabled", {"product": inv.get("antivirus_name")}))
    if inv.get("firewall_enabled") is False:
        issues.append(Issue("firewall_disabled"))
    if inv.get("disk_encrypted") is False and asset_type in {"workstation", "laptop"}:
        issues.append(Issue("disk_not_encrypted"))
    if (inv.get("pending_security_updates") or 0) > 0:
        issues.append(
            Issue(
                "security_updates_pending",
                {
                    "security_updates": inv["pending_security_updates"],
                    "all_updates": inv.get("pending_updates"),
                },
            )
        )
    if unsupported_os(inv.get("os_family"), inv.get("os_name"), inv.get("os_version")):
        issues.append(
            Issue("os_unsupported", {"os": inv.get("os_name"), "version": inv.get("os_version")})
        )
    used = inv.get("disk_used_percent")
    if used is not None and used >= 90:
        issues.append(Issue("disk_space_low", {"disk_used_percent": round(used, 1)}))
    if inv.get("reboot_required") is True:
        issues.append(Issue("reboot_required"))

    os_label = " ".join(p for p in (inv.get("os_name"), inv.get("os_version")) if p) or "Device"
    unknown = [
        k for k in ("antivirus_enabled", "firewall_enabled", "disk_encrypted") if inv.get(k) is None
    ]
    summary = f"{os_label} · {len(issues)} issue(s)" if issues else f"{os_label} · healthy"
    data = {"unknown": unknown, "disk_used_percent": used}
    return Outcome("warning" if issues else "ok", summary, data, issues, reachable=True)
