# Network monitoring (Phase 4)

A cloud platform can't see inside a customer's office network. An **on-premises collector**
runs on a small always-on machine there. It receives approved telemetry and forwards it over an
authenticated, **outbound-only** HTTPS connection. Customers never expose firewall or router
management interfaces to the internet.

```
Firewall / router / switch ──syslog :5514──┐
Suricata sensor (eve.json) ────────────────┼──▶ Collector ──HTTPS (outbound)──▶ Platform
Zeek sensor (notice.log, conn.log) ────────┘       │
                                                   └──▶ reachability checks of authorised devices
```

## What the collector does

| Input | Formats | Forwarded as |
| --- | --- | --- |
| Syslog (UDP/TCP 5514) | FortiGate, Cisco ASA, pfSense/OPNsense, MikroTik, Linux iptables/UFW, SSH on appliances | Blocked connections (aggregated per minute), configuration changes, admin login success/failure, VPN logins |
| Suricata `eve.json` | Alerts | Intrusion detection alerts with signature, category and severity |
| Zeek `notice.log` | JSON or TSV | Notices (e.g. `Scan::Port_Scan`) |
| Zeek `conn.log` | JSON or TSV | Traffic summary only (connections, bytes, top internal talkers), never raw records |
| Probes | TCP connect to the device's port (if given as `host:port`), then 443/22/80/8291/8443, then ping | Reachability and latency of each authorised network device |

**Filtering by design:** allowed-traffic logs are dropped. Only devices on approved address
ranges (private networks by default, configurable) may send syslog. Blocked connections are
aggregated so a flood becomes a handful of events.

**Reliability:** bounded queue (20,000 events, drops counted and reported), large UDP receive
buffer, disk spool on outage or shutdown, exponential backoff, and a heartbeat every minute.

## Packet inspection honesty

Intrusion detection and traffic analysis need a Suricata or Zeek **sensor** on a mirrored switch
port. Without one, the Network page says so plainly and shows "—" rather than implying
protection. Firewall logs and reachability work without a sensor.

## Detections and findings

| Rule | Trigger | Severity |
| --- | --- | --- |
| Network device is unreachable | 3 consecutive failed checks (clears when reachable) | High |
| Collector is dropping events | Dropped events or queue over 10,000 (clears when healthy) | Medium |
| Firewall or router configuration changed | Any config-change log | High |
| Repeated failed logins to a network device | 5+ in 10 minutes | High |
| Network intrusion alert | Suricata severity 1 | High |
| Suspicious network activity | Suricata severity 2; selected Zeek notices | Medium |
| Port scan detected | Zeek `Scan::*` notice, or 500+ blocked connections from one external address in 10 minutes | Medium |

A collector that stops reporting raises "Device has stopped reporting" on the collector's own
asset, like an endpoint agent.

## Security properties

- Separate enrolment tokens (`col_…`) and credentials for collectors. A collector credential
  can't use endpoint-agent APIs and vice versa.
- The server sends the collector only the organisation's own **authorised** network devices to
  probe, and ignores probe results for anything else.
- Device hints in events are matched only against the collector's organisation's assets.
  Unmatched events attach to the collector itself.
- Strict schemas, size and rate limits, idempotent event IDs, and the organisation always taken
  from the enrolled collector.

## Plans

Network collectors are included from the **Professional** plan (2 collectors). Enterprise is
unlimited. Starter and Business show an upgrade prompt.

## Try it

```bash
# After creating a collector token in Network → Add collector:
SMECM_COLLECTOR_TOKEN=col_... docker compose --profile demo up -d demo-collector
docker compose exec demo-collector python /collector/smecm_collector.py \
  --config /state/collector.json simulate config-change      # also: admin-bruteforce, port-scan, ids-alert
```

Register a "router" asset with identifier `web:3000` and confirm authorisation to see a
reachable device in the demo.

## Zeek evaluation

Zeek is worth deploying where a customer can mirror traffic. Its notices (scans, SSH password
guessing, invalid certificates) and connection logs complement Suricata's signatures. We use it
for **summaries and notices only**: raw connection records stay on-site, which keeps bandwidth
and privacy exposure low. Suricata is the primary intrusion detection engine. Both are optional.

## Known gaps

- Signed collector packages and automatic updates (before commercial launch).
- SNMP polling for interface status and bandwidth (planned).
- More vendor formats (Sophos, Ubiquiti, Huawei) as pilot customers need them.
