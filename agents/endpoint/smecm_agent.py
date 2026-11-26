#!/usr/bin/env python3
"""SME Cybersecurity Monitoring: reference endpoint agent.

A small, dependency-free agent for Windows, macOS and Linux. It reports device health
(operating system, firewall, antivirus, disk encryption, updates, disk space) and, on Linux,
sign-in events from the system auth log. For full endpoint detection (malware, process and
Windows event analysis) we recommend the Wazuh agent with our Wazuh connector; this agent is the
lightweight option and the reference for the ingestion API.

Usage:
    python3 smecm_agent.py enrol --server https://monitor.example.com --token enr_...
    python3 smecm_agent.py run            # keep reporting (install as a service)
    python3 smecm_agent.py run --once     # one heartbeat, then exit
    python3 smecm_agent.py inventory      # print what would be reported, send nothing
    python3 smecm_agent.py simulate failed-logins   # send clearly-marked TEST events

The agent only makes outbound HTTPS requests to your monitoring server. It never accepts inbound
connections and never runs commands sent by the server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

VERSION = "1.0.0"
MAX_SPOOL = 5000
EVENT_FLUSH_SECONDS = 30


# --- Config and local state ---------------------------------------------------------------


def default_config_path() -> Path:
    if os.environ.get("SMECM_CONFIG"):
        return Path(os.environ["SMECM_CONFIG"])
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "SMECM" / "agent.json"
    return Path.home() / ".smecm-agent" / "agent.json"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)  # the credential must not be readable by other users
    tmp.replace(path)


def run_cmd(args: list[str], timeout: int = 15) -> str | None:
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


# --- Device identity and inventory ---------------------------------------------------------


def machine_id(state_dir: Path) -> str:
    candidates: list[str | None] = []
    if sys.platform.startswith("linux"):
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                candidates.append(Path(p).read_text().strip())
            except OSError:
                pass
    elif sys.platform == "darwin":
        out = run_cmd(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]) or ""
        m = re.search(r'"IOPlatformUUID" = "([^"]+)"', out)
        candidates.append(m.group(1) if m else None)
    elif sys.platform == "win32":
        out = run_cmd(["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v",
                       "MachineGuid"]) or ""
        m = re.search(r"MachineGuid\s+REG_SZ\s+(\S+)", out)
        candidates.append(m.group(1) if m else None)
    for c in candidates:
        if c and len(c) >= 6:
            return hashlib.sha256(c.encode()).hexdigest()[:48]
    fallback = state_dir / "device-id"
    if not fallback.exists():
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(uuid.uuid4().hex)
    return fallback.read_text().strip()


def _os() -> tuple[str, str | None, str | None]:
    if sys.platform == "darwin":
        return "macos", "macOS", platform.mac_ver()[0] or None
    if sys.platform == "win32":
        release, version = platform.release(), platform.version()
        build = int(version.split(".")[-1]) if version.split(".")[-1].isdigit() else 0
        if release == "10" and build >= 22000:
            release = "11"
        edition = platform.win32_edition() if hasattr(platform, "win32_edition") else ""
        return "windows", f"Windows {release} {edition}".strip(), version
    if sys.platform.startswith("linux"):
        info: dict[str, str] = {}
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k] = v.strip('"')
        except OSError:
            pass
        return "linux", info.get("NAME", "Linux"), info.get("VERSION_ID")
    return "other", platform.system(), platform.release()


def _ip_addresses() -> list[str]:
    ips: set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 80))  # TEST-NET address: no packet is actually sent
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if not ip.startswith(("127.", "::1", "fe80")):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)[:20]


def _memory_mb() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
        except OSError:
            return None
    if sys.platform == "darwin":
        out = run_cmd(["sysctl", "-n", "hw.memsize"])
        return int(out) // (1024 * 1024) if out and out.isdigit() else None
    return None


def _uptime() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            return int(float(Path("/proc/uptime").read_text().split()[0]))
        except (OSError, ValueError):
            return None
    if sys.platform == "darwin":
        out = run_cmd(["sysctl", "-n", "kern.boottime"]) or ""
        m = re.search(r"sec = (\d+)", out)
        return int(time.time()) - int(m.group(1)) if m else None
    return None


def _firewall(family: str) -> bool | None:
    if family == "macos":
        out = run_cmd(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"])
        if out:
            return "enabled" in out.lower()
    if family == "windows":
        out = run_cmd(["netsh", "advfirewall", "show", "allprofiles", "state"])
        if out:
            states = re.findall(r"State\s+(ON|OFF)", out, re.I)
            return bool(states) and all(s.upper() == "ON" for s in states)
    if family == "linux":
        out = run_cmd(["ufw", "status"])
        if out:
            return "status: active" in out.lower()
        out = run_cmd(["firewall-cmd", "--state"])
        if out:
            return out.strip() == "running"
    return None


def _disk_encryption(family: str) -> bool | None:
    if family == "macos":
        out = run_cmd(["fdesetup", "status"])
        if out:
            return "filevault is on" in out.lower()
    if family == "windows":
        out = run_cmd(["manage-bde", "-status", "C:"])
        if out:
            return "protection on" in out.lower()
    if family == "linux":
        out = run_cmd(["lsblk", "-o", "TYPE", "-n"])
        if out:
            return "crypt" in out.split()
    return None


def _antivirus(family: str) -> tuple[bool | None, str | None]:
    if family == "windows":
        out = run_cmd(["powershell", "-NoProfile", "-Command",
                       "(Get-MpComputerStatus).RealTimeProtectionEnabled"])
        if out in {"True", "False"}:
            return out == "True", "Microsoft Defender"
    if family == "macos":
        return None, "XProtect (built in)"
    return None, None


def _updates(family: str) -> tuple[int | None, int | None, bool | None]:
    if family == "linux" and shutil.which("apt"):
        out = run_cmd(["apt", "list", "--upgradable"], timeout=60)
        if out is not None:
            lines = [ln for ln in out.splitlines() if "/" in ln]
            security = [ln for ln in lines if "security" in ln.lower()]
            return len(lines), len(security), Path("/var/run/reboot-required").exists()
    if family == "linux":
        return None, None, Path("/var/run/reboot-required").exists() or None
    return None, None, None


def collect_inventory() -> dict:
    family, os_name, os_version = _os()
    total, used, _ = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\"
                                       if family == "windows" else "/")
    av_enabled, av_name = _antivirus(family)
    pending, pending_security, reboot = _updates(family)
    inventory = {
        "hostname": socket.gethostname()[:255],
        "os_family": family,
        "os_name": os_name,
        "os_version": os_version,
        "kernel": platform.release()[:120],
        "architecture": platform.machine()[:40],
        "uptime_seconds": _uptime(),
        "ip_addresses": _ip_addresses(),
        "cpu_count": os.cpu_count(),
        "memory_total_mb": _memory_mb(),
        "disk_total_gb": round(total / 1e9, 1),
        "disk_used_percent": round(used / total * 100, 1) if total else None,
        "antivirus_enabled": av_enabled,
        "antivirus_name": av_name,
        "firewall_enabled": _firewall(family),
        "disk_encrypted": _disk_encryption(family),
        "pending_updates": pending,
        "pending_security_updates": pending_security,
        "reboot_required": reboot,
    }
    return inventory


# --- Linux sign-in events ------------------------------------------------------------------

_FAILED = re.compile(r"Failed (?:password|publickey) for (?:invalid user )?(\S+) from (\S+)")
_ACCEPTED = re.compile(r"Accepted (?:password|publickey|keyboard-interactive/pam) for (\S+) "
                       r"from (\S+)")


def read_auth_events(state: dict) -> list[dict]:
    path = next((Path(p) for p in ("/var/log/auth.log", "/var/log/secure")
                 if Path(p).exists()), None)
    if path is None:
        return []
    try:
        stat = path.stat()
        cursor = state.get("auth_log", {})
        offset = cursor.get("offset", stat.st_size) if cursor.get("inode") == stat.st_ino \
            else (0 if cursor else stat.st_size)  # first run: start at the end
        if offset > stat.st_size:
            offset = 0  # log rotated
        with path.open("r", errors="replace") as fh:
            fh.seek(offset)
            lines = fh.readlines()[:2000]
            state["auth_log"] = {"inode": stat.st_ino, "offset": fh.tell()}
    except OSError:
        return []
    events = []
    now = datetime.now(UTC).isoformat()
    for line in lines:
        for pattern, event_type in ((_FAILED, "authentication.failure"),
                                    (_ACCEPTED, "authentication.success")):
            m = pattern.search(line)
            if m:
                events.append({
                    "event_id": hashlib.sha256(f"{stat.st_ino}:{line}".encode()).hexdigest()[:40],
                    "event_type": event_type,
                    "timestamp": now,
                    "summary": f"{'Failed' if 'failure' in event_type else 'Successful'} "
                               f"sign-in for {m.group(1)}",
                    "data": {"account": m.group(1)[:120], "source_ip": m.group(2)[:64],
                             "log": str(path)},
                })
    return events


# --- Server communication ------------------------------------------------------------------


class ServerError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def post(server: str, path: str, payload: dict, credential: str | None = None) -> dict:
    data = json.dumps(payload, default=str).encode()
    req = urllib.request.Request(f"{server.rstrip('/')}/api/v1{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", f"smecm-agent/{VERSION}")
    if credential:
        req.add_header("Authorization", f"Agent {credential}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed server URL
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise ServerError(exc.code, exc.read().decode(errors="replace")) from exc


def enrol(server: str, token: str, config_path: Path, allow_http: bool = False) -> None:
    if not server.startswith("https://") and not allow_http:
        sys.exit("Refusing to enrol over plain HTTP. Use your server's https:// address "
                 "(or --allow-insecure-http in an isolated test lab).")
    state_dir = config_path.parent
    payload = {"token": token, "machine_id": machine_id(state_dir), "agent_version": VERSION,
               "inventory": collect_inventory()}
    result = post(server, "/agent/enrol", payload)
    save_json(config_path, {"server": server, "credential": result["credential"],
                            "agent_id": result["agent_id"],
                            "heartbeat_seconds": result["heartbeat_seconds"]})
    print(f"Enrolled. Agent ID {result['agent_id']}. Config saved to {config_path}")


def flush_events(config: dict, spool_path: Path) -> None:
    spool = load_json(spool_path, [])
    while spool:
        batch = spool[:500]
        try:
            post(config["server"], "/agent/events", {"events": batch}, config["credential"])
        except (ServerError, OSError) as exc:
            if isinstance(exc, ServerError) and exc.status == 422:
                spool = spool[len(batch):]  # malformed batch: drop it rather than retry forever
                continue
            break
        spool = spool[len(batch):]
    save_json(spool_path, spool[-MAX_SPOOL:])


def queue_events(events: list[dict], spool_path: Path) -> None:
    if events:
        spool = load_json(spool_path, []) + events
        save_json(spool_path, spool[-MAX_SPOOL:])


def run(config_path: Path, once: bool) -> None:
    config = load_json(config_path, None)
    if not config:
        sys.exit(f"Not enrolled. Run 'enrol' first (no config at {config_path}).")
    state_path = config_path.with_name("state.json")
    spool_path = config_path.with_name("spool.json")
    state = load_json(state_path, {})
    interval = int(os.environ.get("SMECM_HEARTBEAT", config.get("heartbeat_seconds", 300)))
    next_heartbeat = 0.0
    backoff = 5
    while True:
        queue_events(read_auth_events(state), spool_path)
        save_json(state_path, state)
        try:
            if time.monotonic() >= next_heartbeat:
                post(config["server"], "/agent/heartbeat",
                     {"agent_version": VERSION, "inventory": collect_inventory()},
                     config["credential"])
                next_heartbeat = time.monotonic() + interval
                print(f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S} heartbeat sent", flush=True)
            flush_events(config, spool_path)
            backoff = 5
        except ServerError as exc:
            if exc.status == 401:
                sys.exit("The server rejected this agent's credential (revoked?). Re-enrol it.")
            print(f"server error: {exc}; retrying", file=sys.stderr, flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        except OSError as exc:
            # Offline: keep buffering events locally and retry with backoff.
            print(f"cannot reach server ({exc}); buffering", file=sys.stderr, flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        if once:
            return
        time.sleep(EVENT_FLUSH_SECONDS)


def simulate(config_path: Path, kind: str, count: int) -> None:
    """Send clearly-labelled test events so detections can be tried safely."""
    config = load_json(config_path, None)
    if not config:
        sys.exit("Not enrolled.")
    now = datetime.now(UTC).isoformat()
    run_id = uuid.uuid4().hex[:8]
    if kind == "failed-logins":
        events = [{"event_id": f"sim-{run_id}-{i}", "event_type": "authentication.failure",
                   "timestamp": now, "summary": "TEST: simulated failed sign-in",
                   "data": {"account": "admin", "source_ip": "203.0.113.50", "simulated": True}}
                  for i in range(count)]
    elif kind == "malware":
        events = [{"event_id": f"sim-{run_id}-malware", "event_type": "malware.detected",
                   "timestamp": now, "summary": "TEST: EICAR test file detected",
                   "data": {"threat": "EICAR-Test-File (not a real threat)", "simulated": True}}]
    else:
        sys.exit(f"Unknown simulation '{kind}'.")
    result = post(config["server"], "/agent/events", {"events": events}, config["credential"])
    print(f"Sent {result.get('accepted')} test event(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="SME Cybersecurity Monitoring agent")
    parser.add_argument("--config", type=Path, default=default_config_path())
    sub = parser.add_subparsers(dest="command", required=True)
    p_enrol = sub.add_parser("enrol")
    p_enrol.add_argument("--server", required=True)
    p_enrol.add_argument("--token", required=True)
    p_enrol.add_argument("--allow-insecure-http", action="store_true",
                         help="Only for local test labs. Never use on a real network.")
    p_run = sub.add_parser("run")
    p_run.add_argument("--once", action="store_true")
    sub.add_parser("inventory")
    p_sim = sub.add_parser("simulate")
    p_sim.add_argument("kind", choices=["failed-logins", "malware"])
    p_sim.add_argument("--count", type=int, default=12)
    sub.add_parser("version")
    args = parser.parse_args()

    if args.command == "enrol":
        enrol(args.server, args.token, args.config, args.allow_insecure_http)
    elif args.command == "run":
        run(args.config, args.once)
    elif args.command == "inventory":
        print(json.dumps(collect_inventory(), indent=2))
    elif args.command == "simulate":
        simulate(args.config, args.kind, args.count)
    else:
        print(VERSION)


if __name__ == "__main__":
    main()
