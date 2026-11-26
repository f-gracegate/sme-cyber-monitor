#!/usr/bin/env python3
"""SME Cybersecurity Monitoring: on-premises network collector.

Runs inside the customer's network (a small VM, mini PC or Docker host) and forwards approved
network telemetry to the cloud platform over an authenticated, outbound-only HTTPS connection.

* Receives syslog from firewalls, routers and switches (UDP/TCP, default port 5514) and turns
  it into a small set of security events: blocked connections (aggregated), configuration
  changes and admin logins. Allowed-traffic logs are dropped, never forwarded.
* Tails Suricata ``eve.json`` for intrusion-detection alerts, if a Suricata sensor is deployed.
* Tails Zeek ``notice.log`` and summarises ``conn.log`` traffic, if Zeek is deployed.
* Checks that registered, authorised network devices are reachable (TCP connect, then ping).

Nothing listens for commands from the server, and no internal management interface is exposed.

Usage:
    python3 smecm_collector.py enrol --server https://monitor.example.com --token col_...
    python3 smecm_collector.py run
    python3 smecm_collector.py simulate config-change   # clearly-labelled TEST events
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

VERSION = "1.0.0"
MAX_QUEUE = 20_000
BATCH = 500
FLUSH_SECONDS = 5
AGGREGATE_SECONDS = 60
PROBE_PORTS = (443, 22, 80, 8291, 8443)
DEFAULT_ALLOWED = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
                   "fc00::/7", "::1/128"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_config_path() -> Path:
    if os.environ.get("SMECM_COLLECTOR_CONFIG"):
        return Path(os.environ["SMECM_COLLECTOR_CONFIG"])
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "SMECM" / "collector.json"
    return Path.home() / ".smecm-collector" / "collector.json"


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
        os.chmod(tmp, 0o600)
    tmp.replace(path)


_INTERNAL_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "fc00::/7", "fe80::/10", "::1/128")]


def is_internal(ip: str | None) -> bool:
    """Addresses inside an organisation's own network (RFC 1918, CGNAT, ULA, link-local)."""
    try:
        addr = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    return any(addr in net for net in _INTERNAL_NETS)


def _event(event_type: str, device: str | None, summary: str, data: dict,
           severity: str | None = None, count: int = 1, ts: str | None = None) -> dict:
    body = {k: v for k, v in data.items() if v not in (None, "")}
    raw = f"{event_type}|{device}|{summary}|{json.dumps(body, sort_keys=True)}|{ts or time.time()}"
    event = {
        "event_id": hashlib.sha256(raw.encode()).hexdigest()[:40],
        "event_type": event_type,
        "timestamp": ts or now_iso(),
        "summary": summary[:300],
        "device": device,
        "count": count,
        "data": body,
    }
    if severity:
        event["severity"] = severity
    return event


# --- Syslog parsing ------------------------------------------------------------------------

_PRI = re.compile(r"^<\d{1,3}>(?:1 )?")
_KV = re.compile(r'(\w+)=("([^"]*)"|\S+)')
_DENY_WORDS = re.compile(r"\b(DROP|DENY|DENIED|REJECT|BLOCK|BLOCKED)\b", re.I)


def _kv(message: str) -> dict:
    return {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(2))
            for m in _KV.finditer(message)}


def parse_syslog(line: str, sender: str) -> list[dict]:
    """Turn one syslog line into zero or more raw events. Unknown lines are ignored."""
    msg = _PRI.sub("", line.strip())
    if not msg:
        return []
    device = sender

    # Fortinet FortiGate (key="value" pairs)
    if "logid=" in msg and ("type=" in msg or "subtype=" in msg):
        kv = _kv(msg)
        device = kv.get("devname") or device
        desc = (kv.get("logdesc") or kv.get("msg") or "").lower()
        if kv.get("type") == "traffic" and kv.get("action") in {"deny", "blocked", "drop"}:
            return [_event("network.firewall_deny", device, "Blocked connection", {
                "src_ip": kv.get("srcip"), "dst_ip": kv.get("dstip"),
                "dst_port": kv.get("dstport"), "proto": kv.get("proto")})]
        if "admin login failed" in desc:
            return [_event("network.admin_login_failure", device, "Failed admin login",
                           {"user": kv.get("user"), "src_ip": kv.get("srcip")})]
        if "admin login successful" in desc:
            return [_event("network.admin_login_success", device, "Admin login",
                           {"user": kv.get("user"), "src_ip": kv.get("srcip")})]
        if "configuration changed" in desc or kv.get("action") in {"edit", "add", "delete"}:
            return [_event("network.config_change", device, "Configuration changed",
                           {"user": kv.get("user"), "message": kv.get("msg")})]
        if "ssl vpn" in desc and "login" in desc and "success" in desc:
            return [_event("network.vpn_login", device, "VPN login",
                           {"user": kv.get("user"), "src_ip": kv.get("remip")})]
        return []

    # Cisco ASA
    asa = re.search(r"%ASA-\d-(\d{6}): (.*)", msg)
    if asa:
        code, text = asa.groups()
        if code in {"106023", "106001", "106015", "710003"} or text.startswith("Deny"):
            m = re.search(r"src \S+?:([\d.:a-fA-F]+)/(\d+) dst \S+?:([\d.:a-fA-F]+)/(\d+)", text)
            if m:
                return [_event("network.firewall_deny", device, "Blocked connection", {
                    "src_ip": m.group(1), "dst_ip": m.group(3), "dst_port": m.group(4)})]
        if code in {"605004", "113015"}:
            user = re.search(r'user "?([^"\s]+)', text)
            src = re.search(r"from ([\d.:a-fA-F]+)", text)
            return [_event("network.admin_login_failure", device, "Failed admin login", {
                "user": user.group(1) if user else None, "src_ip": src.group(1) if src else None})]
        if code == "605005":
            user = re.search(r'user "?([^"\s]+)', text)
            return [_event("network.admin_login_success", device, "Admin login",
                           {"user": user.group(1) if user else None})]
        if code in {"111008", "111010"}:
            user = re.search(r"User '([^']+)'", text)
            return [_event("network.config_change", device, "Configuration changed",
                           {"user": user.group(1) if user else None, "message": text[:200]})]
        return []

    # pfSense / OPNsense filterlog (CSV)
    if "filterlog" in msg:
        csv = msg.split(":", 1)[-1].strip().split(",")
        try:
            if csv[6] == "block":
                version = csv[8]
                if version == "4" and len(csv) > 21:
                    src, dst, proto = csv[18], csv[19], csv[16]
                    dport = csv[21] if proto in {"tcp", "udp"} else None
                elif version == "6" and len(csv) > 18:
                    src, dst, proto = csv[15], csv[16], csv[12]
                    dport = csv[18] if proto in {"tcp", "udp"} else None
                else:
                    return []
                return [_event("network.firewall_deny", device, "Blocked connection",
                               {"src_ip": src, "dst_ip": dst, "dst_port": dport, "proto": proto})]
        except IndexError:
            return []
        return []

    # Linux netfilter / iptables / UFW
    if "SRC=" in msg and "DST=" in msg and _DENY_WORDS.search(msg):
        kv = _kv(msg)
        return [_event("network.firewall_deny", device, "Blocked connection", {
            "src_ip": kv.get("src"), "dst_ip": kv.get("dst"), "dst_port": kv.get("dpt"),
            "proto": (kv.get("proto") or "").lower() or None})]

    # MikroTik RouterOS
    mt = re.search(r"login failure for user (\S+) from (\S+)", msg)
    if mt:
        return [_event("network.admin_login_failure", device, "Failed admin login",
                       {"user": mt.group(1), "src_ip": mt.group(2)})]
    mt = re.search(r"user (\S+) logged in from (\S+)", msg)
    if mt:
        return [_event("network.admin_login_success", device, "Admin login",
                       {"user": mt.group(1), "src_ip": mt.group(2)})]
    if re.search(r"\b(changed|added|removed) by (\S+)", msg) and "system" in msg.lower():
        user = re.search(r"by (\S+)", msg)
        return [_event("network.config_change", device, "Configuration changed",
                       {"user": user.group(1) if user else None, "message": msg[-200:]})]

    # SSH on network appliances
    ssh = re.search(r"Failed password for (?:invalid user )?(\S+) from (\S+)", msg)
    if ssh:
        return [_event("network.admin_login_failure", device, "Failed admin login",
                       {"user": ssh.group(1), "src_ip": ssh.group(2)})]
    return []


# --- Suricata and Zeek ---------------------------------------------------------------------

_SURICATA_SEVERITY = {1: "high", 2: "medium", 3: "low"}


def parse_suricata(line: str) -> list[dict]:
    try:
        record = json.loads(line)
    except ValueError:
        return []
    if record.get("event_type") != "alert" or not isinstance(record.get("alert"), dict):
        return []
    alert = record["alert"]
    sev = alert.get("severity")
    src, dst = record.get("src_ip"), record.get("dest_ip")
    device = dst if is_internal(dst) else src if is_internal(src) else None
    return [_event(
        "network.ids_alert", device, f"IDS: {alert.get('signature', 'alert')}"[:300], {
            "signature": alert.get("signature"), "category": alert.get("category"),
            "suricata_severity": sev, "signature_id": alert.get("signature_id"),
            "src_ip": src, "dst_ip": dst, "dst_port": record.get("dest_port"),
            "proto": record.get("proto"), "engine": "suricata",
        }, severity=_SURICATA_SEVERITY.get(sev, "low"), ts=_suricata_time(record.get("timestamp")))]


def _suricata_time(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    if len(text) > 5 and text[-5] in "+-" and text[-4:].isdigit():
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return None


class ZeekReader:
    """Reads Zeek logs in JSON or classic tab-separated format."""

    def __init__(self) -> None:
        self.fields: list[str] | None = None

    def records(self, line: str) -> list[dict]:
        line = line.rstrip("\n")
        if not line:
            return []
        if line.startswith("{"):
            try:
                return [json.loads(line)]
            except ValueError:
                return []
        if line.startswith("#fields"):
            self.fields = line.split("\t")[1:]
            return []
        if line.startswith("#") or not self.fields:
            return []
        values = line.split("\t")
        return [{k: (None if v in {"-", "(empty)"} else v) for k, v in zip(self.fields, values)}]


def parse_zeek_notice(record: dict) -> list[dict]:
    note = record.get("note")
    if not note:
        return []
    src, dst = record.get("src") or record.get("id.orig_h"), record.get("dst") or record.get("id.resp_h")
    device = src if is_internal(src) else dst if is_internal(dst) else None
    ts = record.get("ts")
    iso = datetime.fromtimestamp(float(ts), UTC).isoformat() if ts not in (None, "") else None
    return [_event("network.zeek_notice", device, f"Zeek: {note}: {record.get('msg') or ''}"[:300], {
        "note": note, "message": (record.get("msg") or "")[:300], "src_ip": src, "dst_ip": dst,
        "engine": "zeek"}, ts=iso)]


class TrafficStats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.started = time.monotonic()
        self.connections = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.talkers: collections.Counter = collections.Counter()

    def add_conn(self, record: dict) -> None:
        def num(v):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return 0
        with self.lock:
            self.connections += 1
            out_b, in_b = num(record.get("orig_bytes")), num(record.get("resp_bytes"))
            self.bytes_out += out_b
            self.bytes_in += in_b
            host = record.get("id.orig_h")
            if is_internal(host):
                self.talkers[host] += out_b + in_b

    def snapshot(self) -> dict | None:
        with self.lock:
            if self.connections == 0:
                self.started = time.monotonic()
                return None
            data = {
                "window_seconds": max(1, int(time.monotonic() - self.started)),
                "connections": self.connections, "bytes_in": self.bytes_in,
                "bytes_out": self.bytes_out,
                "top_talkers": [{"host": h, "bytes": b} for h, b in self.talkers.most_common(5)],
            }
            self.reset()
            return data


# --- Aggregation and queueing --------------------------------------------------------------


class Pipeline:
    """Bounded queue with aggregation of blocked-connection events."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.queue: collections.deque = collections.deque()
        self.denies: dict[tuple, dict] = {}
        self.window_started = time.monotonic()
        self.dropped = 0
        self.forwarded = 0
        self.sources: dict[str, dict] = {}

    def note_source(self, name: str, kind: str) -> None:
        with self.lock:
            s = self.sources.setdefault(name, {"name": name, "type": kind, "events": 0,
                                               "last_event_at": None})
            s["events"] += 1
            s["last_event_at"] = now_iso()

    def add(self, events: list[dict]) -> None:
        with self.lock:
            for e in events:
                if e["event_type"] == "network.firewall_deny":
                    d = e["data"]
                    key = (e["device"], d.get("src_ip"), d.get("dst_ip"), d.get("dst_port"),
                           d.get("proto"))
                    if key in self.denies:
                        self.denies[key]["count"] += 1
                    else:
                        self.denies[key] = e
                    continue
                self._enqueue(e)

    def _enqueue(self, e: dict) -> None:
        if len(self.queue) >= MAX_QUEUE:
            self.dropped += 1
            return
        self.queue.append(e)

    def roll_aggregates(self, force: bool = False) -> None:
        with self.lock:
            if not force and time.monotonic() - self.window_started < AGGREGATE_SECONDS:
                return
            for e in self.denies.values():
                if e["count"] > 1:
                    e["summary"] = f"{e['count']} blocked connections"
                self._enqueue(e)
            self.denies = {}
            self.window_started = time.monotonic()

    def take(self, n: int) -> list[dict]:
        with self.lock:
            return [self.queue[i] for i in range(min(n, len(self.queue)))]

    def confirm(self, n: int) -> None:
        with self.lock:
            for _ in range(min(n, len(self.queue))):
                self.queue.popleft()
            self.forwarded += n

    def snapshot(self) -> list[dict]:
        with self.lock:
            return list(self.queue) + list(self.denies.values())

    def restore(self, events: list[dict]) -> None:
        with self.lock:
            for e in events[-MAX_QUEUE:]:
                self._enqueue(e)

    def counters(self) -> tuple[int, int]:
        with self.lock:
            dropped, forwarded = self.dropped, self.forwarded
            self.dropped = self.forwarded = 0
            return dropped, forwarded


def probe_plan(address: str) -> tuple[str, tuple[int, ...]]:
    """Host and ports to try. An explicit ``host:port`` is tried first, then the usual
    management ports (HTTPS, SSH, HTTP, MikroTik Winbox, alternate HTTPS)."""
    host = re.sub(r"^\w+://", "", address.strip()).split("/")[0]
    if host.startswith("[") and "]" in host:  # [IPv6]:port
        inner, _, rest = host[1:].partition("]")
        port = rest.lstrip(":")
        return inner, ((int(port),) if port.isdigit() else ()) + PROBE_PORTS
    if host.count(":") == 1:
        host, port = host.split(":")
        if port.isdigit():
            return host, (int(port),) + tuple(p for p in PROBE_PORTS if p != int(port))
    return host, PROBE_PORTS


# --- Listeners and tailers -----------------------------------------------------------------


class Collector:
    def __init__(self, config: dict, config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        self.pipeline = Pipeline()
        self.traffic = TrafficStats()
        self.allowed = [ipaddress.ip_network(c, strict=False)
                        for c in config.get("allowed_sources", DEFAULT_ALLOWED)]
        self.targets: list[dict] = []
        self.probes: list[dict] = []
        self.started = time.monotonic()
        self.capabilities: list[str] = []
        self.listen: dict[str, int] = {}
        self.stop = threading.Event()

    def sender_allowed(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            return False
        return any(addr in net for net in self.allowed)

    def handle_syslog(self, line: str, sender: str) -> None:
        if not self.sender_allowed(sender):
            return  # only devices on approved networks may send logs
        events = parse_syslog(line, sender)
        if events:
            self.pipeline.note_source(f"syslog:{sender}", "syslog")
            self.pipeline.add(events)

    def start_syslog(self) -> None:
        port = int(self.config.get("syslog_port", 5514))
        collector = self

        class UDPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                data = self.request[0].decode("utf-8", errors="replace")
                for line in data.splitlines():
                    collector.handle_syslog(line, self.client_address[0])

        class TCPHandler(socketserver.StreamRequestHandler):
            def handle(self):
                for raw in self.rfile:
                    collector.handle_syslog(raw.decode("utf-8", errors="replace"),
                                            self.client_address[0])

        class BufferedUDPServer(socketserver.UDPServer):
            """One thread with a large receive buffer: parsing is cheap, so bursts of syslog
            are absorbed by the kernel buffer instead of being dropped."""

            def server_bind(self):
                try:
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
                except OSError:
                    pass
                super().server_bind()

        bind = self.config.get("bind", "0.0.0.0")  # noqa: S104 - must receive LAN syslog
        for name, server_cls, handler in (("syslog_udp", BufferedUDPServer, UDPHandler),
                                          ("syslog_tcp", socketserver.ThreadingTCPServer, TCPHandler)):
            try:
                server_cls.allow_reuse_address = True
                server = server_cls((bind, port), handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                self.capabilities.append(name)
                self.listen[name] = port
            except OSError as exc:
                print(f"cannot listen for {name} on {port}: {exc}", file=sys.stderr)

    def tail(self, path: Path, on_line, source: str, kind: str) -> None:
        def run():
            position, inode = None, None
            while not self.stop.is_set():
                try:
                    stat = path.stat()
                    if inode != stat.st_ino or (position or 0) > stat.st_size:
                        inode = stat.st_ino
                        position = stat.st_size if position is None else 0
                    with path.open("r", errors="replace") as fh:
                        fh.seek(position)
                        for line in fh:
                            events = on_line(line)
                            if events:
                                self.pipeline.note_source(source, kind)
                                self.pipeline.add(events)
                        position = fh.tell()
                except OSError:
                    pass
                self.stop.wait(2)
        threading.Thread(target=run, daemon=True).start()

    def start_sensors(self) -> None:
        eve = self.config.get("suricata_eve")
        if eve:
            self.tail(Path(eve), parse_suricata, "suricata", "suricata")
            self.capabilities.append("suricata")
        zeek_dir = self.config.get("zeek_dir")
        if zeek_dir:
            notice_reader, conn_reader = ZeekReader(), ZeekReader()
            self.tail(Path(zeek_dir) / "notice.log",
                      lambda ln: [e for r in notice_reader.records(ln) for e in parse_zeek_notice(r)],
                      "zeek:notice", "zeek")

            def on_conn(ln: str) -> list:
                for record in conn_reader.records(ln):
                    self.traffic.add_conn(record)
                return []
            self.tail(Path(zeek_dir) / "conn.log", on_conn, "zeek:conn", "zeek")
            self.capabilities.append("zeek")

    def probe_once(self) -> None:
        results = []
        for target in list(self.targets):
            host, ports = probe_plan(target["address"])
            result = {"asset_id": target["asset_id"], "reachable": False, "latency_ms": None,
                      "method": None}
            for port in ports:
                started = time.monotonic()
                try:
                    with socket.create_connection((host, port), timeout=2):
                        result.update(reachable=True, method=f"tcp/{port}",
                                      latency_ms=round((time.monotonic() - started) * 1000, 1))
                        break
                except OSError:
                    continue
            if not result["reachable"] and shutil.which("ping"):
                started = time.monotonic()
                flag = "-n" if sys.platform == "win32" else "-c"
                ok = subprocess.run(["ping", flag, "1", host], capture_output=True,  # noqa: S603
                                    timeout=5, check=False).returncode == 0
                if ok:
                    result.update(reachable=True, method="icmp",
                                  latency_ms=round((time.monotonic() - started) * 1000, 1))
            results.append(result)
        self.probes = results
        if "probe" not in self.capabilities:
            self.capabilities.append("probe")

    # --- server communication ---

    def health(self) -> dict:
        dropped, forwarded = self.pipeline.counters()
        with self.pipeline.lock:
            sources = list(self.pipeline.sources.values())[:50]
            depth = len(self.pipeline.queue)
        return {
            "hostname": socket.gethostname()[:255],
            "uptime_seconds": int(time.monotonic() - self.started),
            "queue_depth": depth,
            "events_dropped": dropped,
            "events_forwarded": forwarded,
            "capabilities": sorted(set(self.capabilities)),
            "sources": sources,
            "listen": self.listen,
        }

    def heartbeat(self) -> None:
        payload = {"version": VERSION, "health": self.health(), "probes": self.probes,
                   "traffic": self.traffic.snapshot()}
        response = post(self.config["server"], "/collector/heartbeat", payload,
                        self.config["credential"])
        self.targets = response.get("probe_targets", [])

    def flush(self) -> None:
        self.pipeline.roll_aggregates()
        while True:
            batch = self.pipeline.take(BATCH)
            if not batch:
                return
            try:
                post(self.config["server"], "/collector/events", {"events": batch},
                     self.config["credential"])
            except ServerError as exc:
                if exc.status == 422:
                    self.pipeline.confirm(len(batch))  # malformed: drop, don't retry forever
                    continue
                raise
            self.pipeline.confirm(len(batch))

    @property
    def spool_path(self) -> Path:
        return self.config_path.with_name("spool.json")

    def save_spool(self) -> None:
        """Keep undelivered events on disk so a restart or outage doesn't lose them."""
        save_json(self.spool_path, self.pipeline.snapshot())

    def run(self) -> None:
        self.pipeline.restore(load_json(self.spool_path, []))
        save_json(self.spool_path, [])

        def shutdown(*_):
            self.save_spool()
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        self.start_syslog()
        self.start_sensors()
        next_heartbeat = next_probe = 0.0
        backoff = 5
        while True:
            try:
                if time.monotonic() >= next_probe and self.targets:
                    self.probe_once()
                    next_probe = time.monotonic() + 60
                if time.monotonic() >= next_heartbeat:
                    self.heartbeat()
                    next_heartbeat = time.monotonic() + int(
                        os.environ.get("SMECM_HEARTBEAT", self.config.get("heartbeat_seconds", 60)))
                    print(f"{now_iso()} heartbeat sent; probing {len(self.targets)} device(s)",
                          flush=True)
                self.flush()
                backoff = 5
            except ServerError as exc:
                if exc.status == 401:
                    sys.exit("The server rejected this collector's credential (revoked?). "
                             "Re-enrol it.")
                print(f"server error: {exc}", file=sys.stderr, flush=True)
                self.save_spool()
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            except OSError as exc:
                print(f"cannot reach server ({exc}); buffering", file=sys.stderr, flush=True)
                self.save_spool()
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            time.sleep(FLUSH_SECONDS)


# --- HTTP ----------------------------------------------------------------------------------


class ServerError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def post(server: str, path: str, payload: dict, credential: str | None = None) -> dict:
    req = urllib.request.Request(f"{server.rstrip('/')}/api/v1{path}",
                                 data=json.dumps(payload, default=str).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", f"smecm-collector/{VERSION}")
    if credential:
        req.add_header("Authorization", f"Agent {credential}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed server URL
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise ServerError(exc.code, exc.read().decode(errors="replace")) from exc


def machine_id(state_dir: Path) -> str:
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(p).read_text().strip()
            if len(value) >= 6:
                return "col-" + hashlib.sha256(value.encode()).hexdigest()[:44]
        except OSError:
            pass
    fallback = state_dir / "collector-id"
    if not fallback.exists():
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text("col-" + uuid.uuid4().hex)
    return fallback.read_text().strip()


def enrol(args, config_path: Path) -> None:
    if not args.server.startswith("https://") and not args.allow_insecure_http:
        sys.exit("Refusing to enrol over plain HTTP. Use your server's https:// address "
                 "(or --allow-insecure-http in an isolated test lab).")
    collector = Collector({"server": args.server}, config_path)
    payload = {"token": args.token, "machine_id": machine_id(config_path.parent),
               "version": VERSION, "name": args.name, "health": collector.health()}
    result = post(args.server, "/collector/enrol", payload)
    config = load_json(config_path, {})
    config.update({
        "server": args.server, "credential": result["credential"],
        "collector_id": result["collector_id"], "heartbeat_seconds": result["heartbeat_seconds"],
    })
    config.setdefault("syslog_port", 5514)
    config.setdefault("allowed_sources", DEFAULT_ALLOWED)
    if args.suricata_eve:
        config["suricata_eve"] = args.suricata_eve
    if args.zeek_dir:
        config["zeek_dir"] = args.zeek_dir
    save_json(config_path, config)
    print(f"Enrolled collector {result['collector_id']}. Config saved to {config_path}")


SIMULATIONS = {
    "config-change": ["<189>date=2026-11-26 time=10:00:00 devname=\"FW-HQ\" logid=\"0100044547\" "
                      "type=\"event\" subtype=\"system\" level=\"information\" user=\"admin\" "
                      "action=\"edit\" logdesc=\"Configuration changed\" msg=\"TEST: edit "
                      "firewall.policy 7\""],
    "admin-bruteforce": [f"<38>sshd[123]: Failed password for admin from 203.0.113.77 port {p} ssh2"
                         for p in range(40000, 40008)],
    "port-scan": [f"<4>kernel: [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.66 DST=192.168.1.1 "
                  f"PROTO=TCP SPT=55555 DPT={port} TEST" for port in range(1, 601)],
}
SURICATA_SAMPLE = json.dumps({
    "timestamp": "2026-11-26T10:00:00.000000+0000", "event_type": "alert",
    "src_ip": "192.168.1.25", "src_port": 49822, "dest_ip": "198.51.100.200", "dest_port": 443,
    "proto": "TCP", "alert": {"signature": "TEST ET MALWARE Possible command-and-control beacon",
                              "category": "A Network Trojan was detected", "severity": 1,
                              "signature_id": 2000001}})


def simulate(kind: str, config_path: Path) -> None:
    config = load_json(config_path, None)
    if not config:
        sys.exit("Not enrolled.")
    if kind == "ids-alert":
        events = parse_suricata(SURICATA_SAMPLE)
        for e in events:
            e["data"]["simulated"] = True
        result = post(config["server"], "/collector/events", {"events": events},
                      config["credential"])
        print(f"Sent {result.get('accepted')} test IDS alert(s).")
        return
    # Syslog scenarios go through the running collector's real listener.
    port = int(config.get("syslog_port", 5514))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for line in SIMULATIONS[kind]:
            sock.sendto(line.encode(), ("127.0.0.1", port))
    print(f"Sent {len(SIMULATIONS[kind])} TEST syslog line(s) to 127.0.0.1:{port}. "
          "They're forwarded within a minute.")


def main() -> None:
    parser = argparse.ArgumentParser(description="SME Cybersecurity Monitoring network collector")
    parser.add_argument("--config", type=Path, default=default_config_path())
    sub = parser.add_subparsers(dest="command", required=True)
    p_enrol = sub.add_parser("enrol")
    p_enrol.add_argument("--server", required=True)
    p_enrol.add_argument("--token", required=True)
    p_enrol.add_argument("--name")
    p_enrol.add_argument("--suricata-eve", help="Path to Suricata eve.json")
    p_enrol.add_argument("--zeek-dir", help="Directory with Zeek notice.log and conn.log")
    p_enrol.add_argument("--allow-insecure-http", action="store_true",
                         help="Only for local test labs. Never use on a real network.")
    sub.add_parser("run")
    p_sim = sub.add_parser("simulate")
    p_sim.add_argument("kind", choices=[*SIMULATIONS, "ids-alert"])
    sub.add_parser("version")
    args = parser.parse_args()

    if args.command == "enrol":
        enrol(args, args.config)
    elif args.command == "run":
        config = load_json(args.config, None)
        if not config:
            sys.exit(f"Not enrolled (no config at {args.config}).")
        Collector(config, args.config).run()
    elif args.command == "simulate":
        simulate(args.kind, args.config)
    else:
        print(VERSION)


if __name__ == "__main__":
    main()
