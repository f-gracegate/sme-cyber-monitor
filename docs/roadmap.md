# Roadmap

Estimates are engineering targets, not guaranteed dates. Phases overlap where practical.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation (wk 1–4) | Repo, database, auth + MFA, organisations, tenant isolation, roles, design system, audit log, asset inventory | ✅ Milestone 1 delivered |
| 2. External asset monitoring (wk 5–8) | Scheduler, uptime, DNS, TLS, security headers, email security, findings, alerts, notifications, posture score and trend | ✅ Delivered |
| 3. Endpoint & server monitoring (wk 9–14) | Wazuh evaluation, agent enrolment, health, event ingestion, detection rules, endpoint screens | ✅ Delivered |
| 4. Network monitoring (wk 15–19) | Collector, firewall/device logs, Suricata, Zeek evaluation, network dashboards | ✅ Delivered |
| 5. Incident & risk management (wk 20–22) | Correlation, risk scoring, incidents, remediation, reports | ✅ Delivered |
| 6. Mobile & commercial (wk 23–26) | Flutter Android/iOS, push notifications, billing (MoMo/card), onboarding | Next |
| 7. Pilot & hardening (wk 27–36) | Security and performance testing, regulatory readiness, 5–10 pilot customers | |

## Milestone 1 deliverable

A running application where a business can register, sign in (with MFA), create its
organisation, invite users with roles, and register and authorise its digital assets.

## Phase 2 deliverable

Authorised websites and domains are checked on a schedule (uptime every 5 minutes, DNS hourly,
headers every 6 hours, TLS and email security every 12 hours; all adjustable). 28 plain-English
rules turn results into findings with severity, impact and fix. Repeats are grouped into one
alert; alerts close themselves when the problem clears. Everyone whose role can see alerts gets
in-app notifications (low and above) and email (high and above) by default, each adjustable per
person. The overview shows a posture score, daily trend, findings and alerts by severity,
recent alerts and the most exposed assets.

## Phase 3 deliverable

Devices enrol with short-lived tokens and report through the reference agent or a Wazuh manager.
They become authorised assets automatically, report health (antivirus, firewall, encryption,
updates, disk, OS support) and send security events. Detections cover brute force, sign-in after
brute force, malware, tampering, new admin accounts, log clearing, suspicious processes and
removable media. Silent agents raise a "stopped reporting" finding. See
[endpoints.md](endpoints.md).

## Phase 4 deliverable

An on-premises collector (single Python file or Docker image) receives syslog from common
firewalls and routers, tails Suricata and Zeek output, checks that authorised network devices
are reachable, and forwards filtered, aggregated events over outbound HTTPS. The Network page
shows collectors, device availability, blocked connections, configuration changes and, only
when a sensor exists, intrusion and traffic summaries. See [network.md](network.md).

## Phase 5 deliverable

Critical alerts, and three or more high-severity alerts on one asset within 24 hours, open
incidents automatically. Later alerts on the same asset join the open incident. Responders work
each incident through open, investigating, contained, resolved and closed. Every incident has
an append-only timeline, encrypted evidence with SHA-256 integrity checks, affected assets,
related alerts and containment/recovery tasks. Staff can report suspected incidents and see
only their own reports.

Findings get remediation tasks with owners and due dates set by severity. A task is verified
automatically when monitoring confirms the problem is gone. The posture score (model v2)
combines findings, monitoring coverage, device health, remediation timeliness and open
incidents, and it reports a confidence level. Seven report types are available as PDF, five
of them also as CSV. An executive summary is generated and emailed on the 1st of each month.
See [incidents.md](incidents.md).
