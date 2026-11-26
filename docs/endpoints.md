# Endpoint and server monitoring (Phase 3)

## Two ways to monitor a device

| | SMECM reference agent | Wazuh agent + connector |
| --- | --- | --- |
| What it is | `agents/endpoint/smecm_agent.py`: one Python file, standard library only | The established open-source Wazuh agent, forwarding alerts through our connector |
| Best for | Quick health coverage on Windows, macOS and Linux | Full endpoint detection and response telemetry |
| Device health | OS, firewall, antivirus (Windows), disk encryption, disk space, pending updates and reboots (Linux/apt) | Via Wazuh SCA and inventory (connector forwards alerts today) |
| Security events | Linux sign-ins (auth log) | Malware, Windows events, process and file integrity, sign-ins, plus everything Wazuh rules detect |
| Heartbeat / offline alert | Every 5 minutes; offline after 15 | Not yet: Wazuh agents only send alerts. Poll the Wazuh API for agent status (planned) |
| Enrolment | Short-lived token from **Endpoints → Add devices** | One organisation integration key in **Settings → Integrations** |

**Recommendation (Wazuh evaluation):** for SMEs that need real endpoint detection, run a Wazuh
manager (per customer, or one per managed-service region) on a dedicated Linux VM, not on a
laptop next to the dev stack. Install Wazuh agents on devices and connect the manager with our
connector. Use the reference agent where Wazuh is too heavy, and as the reference for our
ingestion API. Licence: Wazuh is GPLv2. We integrate over its documented integration interface
and don't redistribute it.

## Lifecycle

1. An IT admin creates an enrolment token (valid 1 hour to 7 days, 1–500 uses, device type and
   department). Only a hash is stored. The token is shown once.
2. `smecm_agent.py enrol` sends the token, a stable machine ID and the inventory. The server
   creates the asset, records the agent as **proof of authorisation** and returns a device
   credential. Only its hash is stored. The credential is saved on the device with `0600`
   permissions.
3. `smecm_agent.py run` sends a heartbeat every 5 minutes and flushes buffered events every
   30 seconds. If the server is unreachable, events are buffered locally (up to 5,000) and
   retried with exponential backoff.
4. Revoking the agent invalidates the credential immediately. Re-enrolling the same machine with
   a new token brings it back on the same asset.

## Security properties

- Devices authenticate with `Authorization: Agent <agent_id>:<secret>`, never with user
  sessions. The organisation and asset are taken from the enrolled agent record. Payloads with
  unexpected fields (such as `organisation_id`) are rejected (`extra="forbid"`).
- Strict schemas: known event types only, at most 500 events per batch, 8 KB of data per event,
  body size limits, per-agent rate limits, idempotent event IDs.
- The agent refuses plain HTTP unless `--allow-insecure-http` is passed (local labs only). It
  never accepts inbound connections or remote commands. Containment (isolating devices) is out
  of scope until it has been independently tested.
- Security events are kept 30 days, then pruned. High-volume raw telemetry is meant for an
  event store such as OpenSearch, not for PostgreSQL.

## Detections

| Rule | Trigger | Severity |
| --- | --- | --- |
| Repeated failed sign-ins | 10+ failures on one device within 10 minutes (one failure is never an alert) | High |
| Successful sign-in after repeated failures | Success for an account with 10+ failures in the previous 10 minutes | Critical |
| Malware detected | Malware event from the device or Wazuh | Critical |
| Security protection switched off / new admin account / log cleared / suspicious process | Matching event | High |
| Removable storage connected | USB/removable media event | Low |
| High-severity endpoint alert | Any other Wazuh alert of level 12+ | High |

Detections stay open until a person reviews them. Health findings (antivirus or firewall off,
disk not encrypted on laptops/workstations, security updates pending, unsupported OS, disk over
90% full, restart needed, device stopped reporting) clear automatically on the next healthy
heartbeat. Unknown values never create findings.

## Try it without installing anything

1. In the app: **Endpoints → Add devices**, choose *Server*, create the token.
2. Run a disposable Linux "device" in Docker:

   ```bash
   SMECM_TOKEN=enr_... docker compose --profile demo up -d demo-agent
   ```

3. Trigger clearly-labelled test detections:

   ```bash
   docker compose exec demo-agent python /agent/smecm_agent.py simulate failed-logins
   docker compose exec demo-agent python /agent/smecm_agent.py simulate malware
   ```

## Wazuh connector setup

1. **Settings → Integrations → Create integration key** (shown once).
2. Copy `agents/wazuh/custom-smecm` to `/var/ossec/integrations/custom-smecm` on the manager
   (`chown root:wazuh`, `chmod 750`).
3. Add the `<integration>` block shown in the app to `ossec.conf` and restart the manager.

## Known gaps (tracked for later phases)

- Signed installers and auto-update/rollback for the agent (before commercial launch).
- Tamper detection on the reference agent.
- Wazuh agent status polling (offline detection for Wazuh-managed devices).
- macOS and Windows sign-in events on the reference agent (use Wazuh).
